$ErrorActionPreference = 'Stop'

$python = (Get-Command python -ErrorAction Stop).Source
$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $python
$psi.ArgumentList.Add('-m')
$psi.ArgumentList.Add('unittest')
$psi.ArgumentList.Add('discover')
$psi.ArgumentList.Add('-s')
$psi.ArgumentList.Add('tests')
$psi.ArgumentList.Add('-v')
$psi.WorkingDirectory = (Get-Location).Path
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $psi
if (-not $process.Start()) {
    throw 'Não foi possível iniciar o processo de testes Python.'
}

$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$process.WaitForExit()
$stdoutText = $stdoutTask.GetAwaiter().GetResult()
$stderrText = $stderrTask.GetAwaiter().GetResult()

if ($stdoutText) { [Console]::Out.Write($stdoutText) }
if ($stderrText) { [Console]::Out.Write($stderrText) }

if ($process.ExitCode -ne 0) {
    [Console]::Error.WriteLine("unittest falhou com código de saída $($process.ExitCode).")
}
exit $process.ExitCode
