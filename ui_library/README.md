# Reusable Neon UI

Biblioteca reutilizável de componentes Tkinter e renderizadores de gradiente/neon. O pacote fica separado do downloader e inclui widgets configuráveis, registro de efeitos confiáveis, renderização Pillow opcional, presets, configurações persistentes e testes isolados.

## Requisitos

- Python 3.10+ e Tkinter para os widgets.
- Núcleo sem dependências Python de terceiros.
- Os renderizadores de imagem em `pillow_effects` e `rounded_rendering` usam Pillow opcionalmente; sem Pillow, os módulos continuam importáveis e retornam `None` para renderização de imagem.
- Instalação a partir da raiz: `python -m pip install -e ./ui_library`.

## Exemplo mínimo

```python
import tkinter as tk
from reusable_neon_ui import UIConfig, NeonSurface, NeonButton
root = tk.Tk()
root.geometry("800x500")
settings = UIConfig()
surface = NeonSurface(root, style=settings)
surface.pack(fill="both", expand=True)
label = tk.Label(surface, text="Neon UI", bg="#090814", fg="white")
surface.add_widget(label, x=24, y=24)
button = NeonButton(surface, "Clique", command=lambda: print("clicado"), style=settings)
surface.add_widget(button, x=24, y=70)
root.mainloop()
```

Tkinter não oferece transparência real para widgets nativos: escolha uma cor de fundo compatível para labels colocadas sobre o canvas. Modos disponíveis: `horizontal`, `vertical`, `bottom-up`, `diagonal`, `radial`, `bubbles` e `pulse`.

## Configuração

```python
from reusable_neon_ui import UIConfig, GradientConfig, BorderConfig
settings = UIConfig()
settings.background.gradient = GradientConfig(
    mode="diagonal", colors=("#EC4899", "#8B5CF6", "#2563EB", "#22D3EE"),
    intensity=.86, brightness_min=.12, brightness_max=1.0,
    pulse_strength=.7, pulse_speed=1.4, speed=.7, direction=1)
settings.button.border = BorderConfig(
    enabled=True, colors=("#EC4899", "#8B5CF6", "#22D3EE"),
    thickness=2.5, intensity=.95, glow=5, speed=1.0, animation="flow")
settings.tab.gradient.mode = "bubbles"
settings.tab.gradient.bubble_count = 9
settings.reduced_motion = False
```

Fundo, botão e aba têm estilos independentes. Intensidade mistura a paleta com a cor de base; brilho mínimo/máximo e força/velocidade do pulso controlam a variação; velocidade/direção controlam o movimento. Bordas neon aceitam cores, espessura, intensidade, glow e animação `flow`, `pulse` ou `static`. Use `UIConfig(reduced_motion=True)` para desativar a animação.

## Persistência e efeitos adicionais

```python
from pathlib import Path
from reusable_neon_ui import UIConfig, save_config, load_config
path = Path.home() / ".myapp" / "neon-ui.json"
save_config(path, settings)
settings = load_config(path)
```

A gravação é atômica, valores são validados e links simbólicos no arquivo-alvo são rejeitados. O esquema atual é 1.

Efeitos novos são código Python confiável integrado pelo desenvolvedor, nunca scripts baixados:

```python
from reusable_neon_ui import register_effect
def cyan_magenta(config, x, y, phase):
    return "#FF00CC" if (x + phase * .1) % 1 < .5 else "#00D9FF"
register_effect("cyan_magenta", cyan_magenta)
settings.background.gradient.mode = "cyan_magenta"
```

O renderer recebe configuração, x/y normalizados e fase e retorna HEX. Não execute plugins de mídia ou URLs. Renderizadores devem evitar rede, I/O e cálculos caros.

## Renderizadores reutilizados do app

- `render_ambient_gradient`, `render_gradient_preview`, `render_atom_art`: geração de imagem/arte, com Pillow opcional.
- `render_rounded_panel`, `render_rounded_button`: superfícies arredondadas antialiasadas, com Pillow opcional.
- `NeonSurface`, `NeonButton`, `NeonTabBar`: widgets Tkinter animados.

O glow dos widgets é simulado por contornos concêntricos, não por blur de GPU. A biblioteca não reproduz vídeo nem altera o papel de parede do Windows; esses recursos continuam no aplicativo principal.

## Testes e pacote ZIP

```bash
python -m unittest discover -s ui_library/tests -v
python -m compileall -q ui_library/src ui_library/tests
python ui_library/tools/package.py
```

O workflow GitHub Actions executa testes em Ubuntu/Windows e Python 3.10/3.12 e gera um artefato ZIP da biblioteca. O repositório usa MIT; preserve o aviso de `LICENSE` ao redistribuir.
