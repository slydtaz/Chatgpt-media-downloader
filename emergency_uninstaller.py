from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import sys
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk, simpledialog
from typing import Mapping

APP_TITLE = "GPT Media Uninstaller"
VENDOR = "ChatGPT"
PRODUCT_ID = "com.chatgpt.mediadownloader"
INSTALL_PREFIX = "MediaDownloader-com.chatgpt.mediadownloader-"
INSTALL_MARKER = ".chatgpt-media-downloader-install.json"
PROJECT_MARKER = "PROJECT_ID"
UNINSTALL_LOG = "GPT-Media-Uninstaller.log"
MEDIA_CONFIRMATION = "APAGAR MIDIAS"


@dataclass(frozen=True)
class FolderCandidate:
    path: Path
    verified: bool
    note: str


@dataclass(frozen=True)
class OutputCandidate:
    path: Path
    safe_to_remove: bool
    exists: bool
    note: str


@dataclass
class CleanupPlan:
    data_dir: Path
    data_exists: bool
    install_dirs: list[FolderCandidate]
    shortcuts: list[Path]
    portable_files: list[Path]
    portable_dirs: list[FolderCandidate]
    output_dirs: list[OutputCandidate]


def _dedupe(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(os.path.abspath(str(path)))
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def _context(env: Mapping[str, str] | None = None) -> dict[str, str]:
    result = dict(os.environ if env is None else env)
    home = result.get("USERPROFILE") or str(Path.home())
    local = result.get("LOCALAPPDATA") or str(Path(home) / "AppData" / "Local")
    roaming = result.get("APPDATA") or str(Path(home) / "AppData" / "Roaming")
    result["USERPROFILE"] = home
    result["LOCALAPPDATA"] = local
    result["APPDATA"] = roaming
    return result


def _marker_status(path: Path) -> tuple[str, bool]:
    marker_path = path / INSTALL_MARKER
    if not marker_path.is_file():
        return "sem marcador (instalação antiga ou incompleta)", False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "marcador inválido (instalação antiga ou incompleta)", False
    if marker.get("vendor") == VENDOR and marker.get("product_id") == PRODUCT_ID:
        return "propriedade confirmada pelo marcador", True
    return "marcador pertence a outro produto; preservado", False


def _known_chatgpt_roots(ctx: Mapping[str, str]) -> list[Path]:
    roots: list[Path] = []
    local = Path(ctx["LOCALAPPDATA"])
    roots.append(local / "Programs" / "ChatGPT")
    for key in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        value = ctx.get(key, "").strip()
        if value:
            roots.append(Path(value) / "ChatGPT")
    if not any(ctx.get(key) for key in ("ProgramW6432", "ProgramFiles")):
        roots.append(Path(r"C:\Program Files") / "ChatGPT")
    if not ctx.get("ProgramFiles(x86)"):
        roots.append(Path(r"C:\Program Files (x86)") / "ChatGPT")
    return _dedupe(roots)


def _source_copy_identity(path: Path) -> bool:
    marker = path / PROJECT_MARKER
    if not marker.is_file():
        return False
    try:
        return marker.read_text(encoding="utf-8", errors="replace").strip() == PRODUCT_ID
    except OSError:
        return False


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def _safe_output_dir(path: Path, home: Path, one_drive: Path | None,
                     data_dir: Path, install_dirs: list[FolderCandidate]) -> tuple[bool, str]:
    try:
        target = path.expanduser().resolve(strict=False)
        home_resolved = home.resolve(strict=False)
    except (OSError, RuntimeError):
        return False, "caminho não pôde ser validado"

    if not target.is_absolute() or target == Path(target.anchor):
        return False, "caminho amplo demais"
    if target == home_resolved or _is_within(data_dir, target):
        return False, "não é uma pasta de mídia dedicada"
    if target == data_dir.resolve(strict=False) or _is_within(target, data_dir):
        return False, "fica dentro dos dados internos do aplicativo"
    if any(target == item.path.resolve(strict=False) or _is_within(target, item.path)
           for item in install_dirs):
        return False, "fica dentro da instalação do aplicativo"

    special: list[Path] = []
    for name in ("Desktop", "Downloads", "Documents", "Music", "Videos", "Pictures"):
        special.append(home_resolved / name)
    if one_drive:
        od = one_drive.resolve(strict=False)
        special.extend(od / name for name in ("Desktop", "Downloads", "Documents", "Music", "Pictures", "Videos"))
        if target == od:
            return False, "pasta raiz do OneDrive"
    if any(target == item.resolve(strict=False) for item in special):
        return False, "pasta pessoal padrão, não dedicada ao aplicativo"

    allowed_roots = [home_resolved]
    if one_drive:
        allowed_roots.append(one_drive.resolve(strict=False))
    if not any(_is_within(target, root) for root in allowed_roots):
        return False, "fora da pasta do usuário; preservado por segurança"

    relative_parts = None
    for root in allowed_roots:
        try:
            relative_parts = len(target.relative_to(root).parts)
            break
        except ValueError:
            continue
    if relative_parts is None or relative_parts < 2:
        return False, "pasta não parece suficientemente específica"

    if target.exists() and target.is_symlink():
        return False, "link simbólico; preservado por segurança"
    return True, "pasta configurada; apagar somente com confirmação adicional"


def discover_targets(env: Mapping[str, str] | None = None) -> CleanupPlan:
    ctx = _context(env)
    home = Path(ctx["USERPROFILE"]).expanduser()
    local = Path(ctx["LOCALAPPDATA"]).expanduser()
    roaming = Path(ctx["APPDATA"]).expanduser()
    data_dir = local / "ChatGPT" / "MediaDownloader"

    install_dirs: list[FolderCandidate] = []
    for root in _known_chatgpt_roots(ctx):
        try:
            if not root.is_dir() or root.is_symlink():
                continue
            for child in root.iterdir():
                if not child.is_dir() or child.is_symlink():
                    continue
                if not child.name.casefold().startswith(INSTALL_PREFIX.casefold()):
                    continue
                note, verified = _marker_status(child)
                if note.startswith("marcador pertence a outro produto"):
                    continue
                # Only direct child folders with our product-specific prefix under a
                # known ChatGPT installation parent are eligible, including unmarked
                # partial/legacy installs from failed updates.
                try:
                    if child.resolve().parent != root.resolve():
                        continue
                except OSError:
                    continue
                install_dirs.append(FolderCandidate(child, verified, note))
        except OSError:
            continue

    desktops = [home / "Desktop"]
    downloads = [home / "Downloads"]
    one_drive = Path(ctx["OneDrive"]).expanduser() if ctx.get("OneDrive", "").strip() else None
    if one_drive:
        desktops.append(one_drive / "Desktop")
        downloads.append(one_drive / "Downloads")

    roaming_start = roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    program_data = Path(ctx.get("PROGRAMDATA") or r"C:\ProgramData")
    common_start = program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    shortcut_dirs = desktops + [roaming_start, common_start, program_data / "Microsoft" / "Windows" / "Start Menu"]
    shortcut_candidates = [p / "ChatGPT Media Downloader.lnk" for p in _dedupe(shortcut_dirs)]
    shortcuts = [p for p in shortcut_candidates if p.is_file() and not p.is_symlink()]

    portable_files: list[Path] = []
    portable_dirs: list[FolderCandidate] = []
    for folder in _dedupe(desktops + downloads):
        try:
            if not folder.is_dir() or folder.is_symlink():
                continue
            for child in folder.iterdir():
                if child.is_file() and not child.is_symlink() and child.name.casefold() == "chatgptmediadownloader.exe":
                    portable_files.append(child)
                elif child.is_dir() and not child.is_symlink() and _source_copy_identity(child):
                    portable_dirs.append(FolderCandidate(child, True, "PROJECT_ID do projeto confirmado"))
        except OSError:
            continue

    config_path = data_dir / "config" / "config.json"
    configured_outputs: list[Path] = []
    try:
        if config_path.is_file():
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(config, dict):
                for key in ("music_dir", "video_dir"):
                    value = str(config.get(key) or "").strip()
                    if value:
                        value = os.path.expandvars(value)
                        output = Path(value).expanduser()
                        if not output.is_absolute():
                            continue
                        configured_outputs.append(output)
    except (OSError, json.JSONDecodeError, ValueError):
        pass

    install_dirs = _unique_candidates(install_dirs)
    output_dirs: list[OutputCandidate] = []
    for output in _dedupe(configured_outputs):
        safe, note = _safe_output_dir(output, home, one_drive, data_dir, install_dirs)
        output_dirs.append(OutputCandidate(output, safe, output.is_dir() and not output.is_symlink(), note))

    return CleanupPlan(
        data_dir=data_dir,
        data_exists=data_dir.is_dir() and not data_dir.is_symlink(),
        install_dirs=_unique_candidates(install_dirs),
        shortcuts=_dedupe(shortcuts),
        portable_files=_dedupe(portable_files),
        portable_dirs=_unique_candidates(portable_dirs),
        output_dirs=output_dirs,
    )


def _unique_candidates(items: list[FolderCandidate]) -> list[FolderCandidate]:
    out: list[FolderCandidate] = []
    seen: set[str] = set()
    for item in items:
        key = os.path.normcase(os.path.abspath(str(item.path)))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _write_log(lines: list[str], ctx: Mapping[str, str]) -> Path | None:
    candidates = [
        Path(ctx.get("TEMP") or tempfile.gettempdir()) / UNINSTALL_LOG,
        Path(tempfile.gettempdir()) / UNINSTALL_LOG,
    ]
    for path in _dedupe(candidates):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n")
                for line in lines:
                    handle.write(line.rstrip() + "\n")
            return path
        except OSError:
            continue
    return None


def _remove_tree_preserving(root: Path, preserve: list[Path], log: list[str]) -> None:
    root = root.resolve(strict=False)
    if not root.exists():
        return
    if root.is_symlink() or root == Path(root.anchor):
        raise RuntimeError(f"Recusa de apagar caminho inseguro: {root}")

    preserved = [p.resolve(strict=False) for p in preserve if p.exists()]
    for child in list(root.iterdir()):
        child_resolved = child.resolve(strict=False)
        exact_preserve = any(child_resolved == p for p in preserved)
        ancestor_of_preserve = any(_is_within(p, child_resolved) for p in preserved)
        if exact_preserve:
            log.append(f"PRESERVADO (pasta de mídia escolhida pelo usuário): {child}")
            continue
        if ancestor_of_preserve and child.is_dir() and not child.is_symlink():
            _remove_tree_preserving(child, preserved, log)
            continue
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
            log.append(f"REMOVIDO: {child}")
        except OSError as exc:
            log.append(f"FALHA: {child} — {exc}")
    try:
        if not any(_is_within(p, root) for p in preserved):
            root.rmdir()
            log.append(f"REMOVIDO: {root}")
    except OSError as exc:
        log.append(f"FALHA: {root} — {exc}")


def perform_cleanup(plan: CleanupPlan, *, remove_portable: bool = False,
                    remove_media: bool = False,
                    env: Mapping[str, str] | None = None) -> list[str]:
    ctx = _context(env)
    log: list[str] = []
    media_to_preserve = [item.path for item in plan.output_dirs if item.exists and (not remove_media or not item.safe_to_remove)]
    if remove_media:
        for item in plan.output_dirs:
            if not item.exists:
                continue
            if not item.safe_to_remove:
                log.append(f"PRESERVADO por segurança (pasta não dedicada): {item.path}")
                continue
            try:
                if item.path.is_symlink():
                    raise RuntimeError("A pasta de mídia tornou-se um link simbólico; exclusão cancelada.")
                resolved = item.path.resolve(strict=True)
                if resolved == Path(resolved.anchor) or resolved == Path(ctx["USERPROFILE"]).resolve():
                    raise RuntimeError("Caminho de mídia amplo demais.")
                shutil.rmtree(resolved)
                log.append(f"MÍDIA REMOVIDA conforme confirmação explícita: {resolved}")
            except (OSError, RuntimeError) as exc:
                log.append(f"FALHA ao apagar mídia {item.path}: {exc}")

    for shortcut in plan.shortcuts:
        try:
            shortcut.unlink(missing_ok=True)
            log.append(f"ATALHO REMOVIDO: {shortcut}")
        except OSError as exc:
            log.append(f"FALHA: {shortcut} — {exc}")

    for candidate in plan.install_dirs:
        try:
            path = candidate.path.resolve(strict=True)
            if not path.name.casefold().startswith(INSTALL_PREFIX.casefold()):
                raise RuntimeError("O nome da pasta mudou; limpeza cancelada.")
            if candidate.path.is_symlink():
                raise RuntimeError("A pasta se tornou um link simbólico.")
            shutil.rmtree(path)
            log.append(f"INSTALAÇÃO REMOVIDA: {path} ({candidate.note})")
        except (OSError, RuntimeError) as exc:
            log.append(f"FALHA ao remover instalação {candidate.path}: {exc}")

    if remove_portable:
        for candidate in plan.portable_dirs:
            try:
                if not _source_copy_identity(candidate.path):
                    raise RuntimeError("PROJECT_ID deixou de corresponder ao aplicativo.")
                shutil.rmtree(candidate.path)
                log.append(f"CÓPIA-FONTE REMOVIDA: {candidate.path}")
            except (OSError, RuntimeError) as exc:
                log.append(f"FALHA ao remover cópia-fonte {candidate.path}: {exc}")
        for file in plan.portable_files:
            try:
                if file.is_symlink() or file.name.casefold() != "chatgptmediadownloader.exe":
                    raise RuntimeError("O arquivo deixou de corresponder ao nome esperado.")
                file.unlink(missing_ok=True)
                log.append(f"EXECUTÁVEL PORTÁTIL REMOVIDO: {file}")
            except (OSError, RuntimeError) as exc:
                log.append(f"FALHA ao remover cópia portátil {file}: {exc}")

    # Delete application cache, configuration, bundled tools and logs, but preserve
    # any custom media output folder nested inside the app-data tree unless opted in.
    try:
        if plan.data_dir.is_symlink():
            raise RuntimeError("A pasta de dados é um link simbólico; limpeza cancelada.")
        _remove_tree_preserving(plan.data_dir, media_to_preserve, log)
    except (OSError, RuntimeError) as exc:
        log.append(f"FALHA ao remover dados {plan.data_dir}: {exc}")

    log_path = _write_log(log, ctx)
    if log_path:
        log.append(f"RELATÓRIO DA LIMPEZA: {log_path}")
    return log


def _is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _requires_elevation(plan: CleanupPlan, env: Mapping[str, str] | None = None) -> bool:
    if os.name != "nt" or _is_admin():
        return False
    ctx = _context(env)
    roots = []
    for key in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        value = ctx.get(key, "").strip()
        if value:
            roots.append(Path(value))
    roots = _dedupe(roots)
    return any(any(_is_within(item.path, root) for root in roots) for item in plan.install_dirs)


def _context_cli(ctx: Mapping[str, str]) -> list[str]:
    result: list[str] = []
    for arg, key in (
        ("--home-root", "USERPROFILE"),
        ("--local-app-data", "LOCALAPPDATA"),
        ("--roaming-app-data", "APPDATA"),
        ("--program-data", "PROGRAMDATA"),
        ("--one-drive", "OneDrive"),
        ("--temp-root", "TEMP"),
    ):
        value = ctx.get(key, "").strip()
        if value:
            result.extend([arg, value])
    return result


def _restart_elevated(remove_portable: bool, remove_media: bool,
                      env: Mapping[str, str]) -> None:
    args = ["--confirmed-cleanup"]
    if remove_portable:
        args.append("--remove-portable")
    if remove_media:
        args.append("--remove-media")
    args.extend(_context_cli(_context(env)))
    if getattr(sys, "frozen", False):
        executable = sys.executable
        parameters = subprocess.list2cmdline(args)
    else:
        executable = sys.executable
        parameters = subprocess.list2cmdline([str(Path(__file__).resolve()), *args])
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", executable, parameters, None, 1
    )
    if result <= 32:
        raise OSError(f"O Windows recusou a elevação (código {result}).")


def _build_report(plan: CleanupPlan) -> str:
    lines = [
        f"Dados e configurações: {plan.data_dir} ({'encontrados' if plan.data_exists else 'não encontrados'})",
    ]
    if plan.install_dirs:
        for item in plan.install_dirs:
            lines.append(f"Instalação: {item.path} — {item.note}")
    else:
        lines.append("Instalações registradas: nenhuma pasta encontrada nos locais conhecidos.")
    if plan.shortcuts:
        lines.extend(f"Atalho: {item}" for item in plan.shortcuts)
    else:
        lines.append("Atalhos: nenhum atalho com o nome do aplicativo encontrado.")
    lines.append("Cópias portáteis/fontes opcionais:")
    lines.extend(f"  EXE: {item}" for item in plan.portable_files)
    lines.extend(f"  Fonte: {item.path}" for item in plan.portable_dirs)
    if not plan.portable_files and not plan.portable_dirs:
        lines.append("  Nenhuma cópia extra encontrada na Área de Trabalho/Downloads.")
    lines.append("Pastas configuradas para músicas/vídeos (preservadas por padrão):")
    for item in plan.output_dirs:
        state = "existe" if item.exists else "não existe"
        safety = "pode ser selecionada" if item.safe_to_remove else "será preservada"
        lines.append(f"  {item.path} — {state}; {safety}")
    if not plan.output_dirs:
        lines.append("  Não foi possível encontrar pastas configuradas.")
    return "\n".join(lines)


class UninstallerWindow:
    def __init__(self, env: Mapping[str, str] | None = None):
        self.env = _context(env)
        self.plan = discover_targets(self.env)
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("820x720")
        self.root.minsize(720, 610)
        self.root.configure(bg="#0D1220")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#0D1220")
        style.configure("TLabel", background="#0D1220", foreground="#EDF2FF")
        style.configure("Muted.TLabel", background="#0D1220", foreground="#A9B5CD")
        style.configure("Danger.TButton", padding=(16, 10))
        style.configure("TCheckbutton", background="#0D1220", foreground="#EDF2FF")

        body = ttk.Frame(self.root, padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="GPT Media Uninstaller", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            body,
            text="Ferramenta emergencial para remover o ChatGPT Media Downloader.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 14))
        ttk.Label(
            body,
            text=(
                "A remoção padrão apaga as instalações localizadas, configurações, logs, cache, "
                "ferramentas empacotadas e atalhos do aplicativo. Não remove Python, programas "
                "de terceiros nem suas mídias baixadas automaticamente."
            ),
            wraplength=740,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        report_frame = ttk.Frame(body)
        report_frame.pack(fill="both", expand=True)
        self.report = tk.Text(
            report_frame, wrap="word", height=18, bg="#131B2C", fg="#DCE6FC",
            insertbackground="#FFFFFF", relief="flat", padx=12, pady=10,
        )
        scrollbar = ttk.Scrollbar(report_frame, orient="vertical", command=self.report.yview)
        self.report.configure(yscrollcommand=scrollbar.set)
        self.report.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.report.insert("1.0", _build_report(self.plan))
        self.report.configure(state="disabled")

        self.remove_portable_var = tk.BooleanVar(value=False)
        self.remove_media_var = tk.BooleanVar(value=False)
        self.remove_self_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            body, text="Também remover EXEs portáteis e pastas-fonte detectados em Desktop/Downloads",
            variable=self.remove_portable_var,
        ).pack(anchor="w", pady=(11, 2))
        ttk.Checkbutton(
            body, text="Também apagar TODAS as mídias dentro das pastas configuradas listadas acima (irreversível)",
            variable=self.remove_media_var,
        ).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            body, text="Apagar este desinstalador depois de concluir",
            variable=self.remove_self_var,
        ).pack(anchor="w", pady=2)
        ttk.Label(
            body,
            text=(
                "Cuidado: a opção de mídias apaga a pasta configurada inteira, incluindo qualquer arquivo "
                "pessoal que esteja nela. Pastas genéricas ou fora do perfil do usuário serão preservadas."
            ),
            style="Muted.TLabel",
            wraplength=740,
            justify="left",
        ).pack(anchor="w", pady=(3, 12))

        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancelar", command=self.root.destroy).pack(side="right")
        ttk.Button(actions, text="Remover o aplicativo", style="Danger.TButton", command=self.remove).pack(side="right", padx=(0, 9))

    def remove(self):
        plan = discover_targets(self.env)
        self.plan = plan
        remove_portable = bool(self.remove_portable_var.get())
        remove_media = bool(self.remove_media_var.get())
        remove_self = bool(self.remove_self_var.get())

        if remove_media:
            paths = [str(item.path) for item in plan.output_dirs if item.exists and item.safe_to_remove]
            if not paths:
                messagebox.showwarning(APP_TITLE, "Não encontrei nenhuma pasta de mídia segura e existente para excluir.", parent=self.root)
                return
            phrase = simpledialog.askstring(
                APP_TITLE,
                "A ação abaixo apagará todos os arquivos das pastas:\n\n"
                + "\n".join(paths)
                + "\n\nPara confirmar essa exclusão irreversível, digite APAGAR MIDIAS:",
                parent=self.root,
            )
            if phrase != MEDIA_CONFIRMATION:
                messagebox.showinfo(APP_TITLE, "Exclusão de mídias cancelada. As pastas de saída serão preservadas.", parent=self.root)
                return

        selected_portable = plan.portable_files + [item.path for item in plan.portable_dirs] if remove_portable else []
        selected_media = [item.path for item in plan.output_dirs if item.exists and item.safe_to_remove] if remove_media else []
        prompt = (
            "Confirma remover as instalações, configurações, logs, cache e atalhos listados?\n\n"
            f"Instalações encontradas: {len(plan.install_dirs)}\n"
            f"Pasta de dados: {'sim' if plan.data_exists else 'não'}\n"
            f"Atalhos: {len(plan.shortcuts)}\n"
            f"Cópias extras selecionadas: {len(selected_portable)}\n"
            f"Pastas de mídia selecionadas: {len(selected_media)}\n\n"
            "Arquivos de música/vídeo serão preservados, a menos que você tenha selecionado e confirmado "
            "explicitamente a exclusão das pastas de mídia. Não será removido nenhum outro aplicativo."
        )
        if not messagebox.askyesno(APP_TITLE, prompt, icon="warning", parent=self.root):
            return

        if _requires_elevation(plan, self.env):
            try:
                _restart_elevated(remove_portable, remove_media, self.env)
            except OSError as exc:
                messagebox.showerror(APP_TITLE, f"Não foi possível solicitar permissão do Windows:\n{exc}", parent=self.root)
                return
            messagebox.showinfo(
                APP_TITLE,
                "O Windows abriu a cópia elevada do desinstalador. Se você aceitou o pedido de permissão, "
                "a limpeza continuará nessa janela.",
                parent=self.root,
            )
            self.root.destroy()
            return

        log = perform_cleanup(plan, remove_portable=remove_portable, remove_media=remove_media, env=self.env)
        failures = [line for line in log if line.startswith("FALHA:") or line.startswith("FALHA ao")]
        preserved_media = [line for line in log if line.startswith("PRESERVADO (pasta de mídia")]
        if failures:
            message = (
                "A limpeza terminou parcialmente; alguns caminhos não puderam ser removidos.\n\n"
                + "\n".join(failures[:12])
                + "\n\nFeche processos do aplicativo ou execute novamente com as permissões adequadas."
            )
            messagebox.showwarning(APP_TITLE, message, parent=self.root)
        else:
            message = (
                "Limpeza concluída para todos os caminhos do aplicativo que foram encontrados e puderam ser removidos.\n\n"
                "As pastas de saída não selecionadas continuam preservadas, pois podem conter seus arquivos pessoais."
            )
            if preserved_media:
                message += "\n\n" + "\n".join(preserved_media[:5])
            messagebox.showinfo(APP_TITLE, message, parent=self.root)

        if remove_self and getattr(sys, "frozen", False):
            try:
                if not schedule_self_delete():
                    messagebox.showwarning(
                        APP_TITLE,
                        "A limpeza terminou, mas não foi possível agendar a remoção automática do executável. "
                        "Se ele continuar na pasta de downloads após reiniciar, remova-o manualmente.",
                        parent=self.root,
                    )
            except OSError as exc:
                messagebox.showwarning(
                    APP_TITLE,
                    "A limpeza terminou, mas o Windows não conseguiu agendar a remoção do desinstalador. "
                    f"Detalhe: {exc}",
                    parent=self.root,
                )
        self.root.destroy()


def schedule_self_delete() -> bool:
    """Schedule this frozen helper for deletion at reboot without launching a shell."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    executable = Path(sys.executable).resolve()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move_file_ex = kernel32.MoveFileExW
    move_file_ex.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    move_file_ex.restype = ctypes.c_int
    MOVEFILE_DELAY_UNTIL_REBOOT = 0x00000004
    if not move_file_ex(str(executable), None, MOVEFILE_DELAY_UNTIL_REBOOT):
        raise ctypes.WinError(ctypes.get_last_error())
    return True


def _parse_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--confirmed-cleanup", action="store_true")
    parser.add_argument("--remove-portable", action="store_true")
    parser.add_argument("--remove-media", action="store_true")
    parser.add_argument("--home-root")
    parser.add_argument("--local-app-data")
    parser.add_argument("--roaming-app-data")
    parser.add_argument("--program-data")
    parser.add_argument("--one-drive")
    parser.add_argument("--temp-root")
    return parser.parse_args()


def _context_from_args(args) -> dict[str, str]:
    ctx = _context()
    fields = {
        "home_root": "USERPROFILE",
        "local_app_data": "LOCALAPPDATA",
        "roaming_app_data": "APPDATA",
        "program_data": "PROGRAMDATA",
        "one_drive": "OneDrive",
        "temp_root": "TEMP",
    }
    for arg_name, env_name in fields.items():
        value = getattr(args, arg_name, None)
        if value:
            ctx[env_name] = value
    return ctx


def main() -> int:
    args = _parse_args()
    ctx = _context_from_args(args)

    if args.confirmed_cleanup:
        root = tk.Tk()
        root.withdraw()
        try:
            plan = discover_targets(ctx)
            log = perform_cleanup(
                plan,
                remove_portable=args.remove_portable,
                remove_media=args.remove_media,
                env=ctx,
            )
            failures = [line for line in log if line.startswith("FALHA:") or line.startswith("FALHA ao")]
            if failures:
                messagebox.showwarning(
                    APP_TITLE,
                    "Limpeza elevada terminou parcialmente:\n\n" + "\n".join(failures[:12]),
                    parent=root,
                )
            else:
                messagebox.showinfo(
                    APP_TITLE,
                    "Limpeza elevada concluída para os caminhos encontrados. Consulte "
                    + str(Path(ctx.get("TEMP") or tempfile.gettempdir()) / UNINSTALL_LOG),
                    parent=root,
                )
        finally:
            root.destroy()
        return 0

    app = UninstallerWindow(ctx)
    app.root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
