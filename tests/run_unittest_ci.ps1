$ErrorActionPreference = 'Stop'

$python = Get-Command python -ErrorAction Stop
$tempRoot = $env:RUNNER_TEMP
if ([string]::IsNullOrWhiteSpace($tempRoot)) {
    $tempRoot = [System.IO.Path]::GetTempPath()
}
$token = [Guid]::NewGuid().ToString('N')
$stdoutPath = Join-Path $tempRoot "unittest-$token.stdout.log"
$stderrPath = Join-Path $tempRoot "unittest-$token.stderr.log"

try {
    $startInfo = @{
        FilePath = $python.Source
        ArgumentList = @('-m', 'unittest', 'discover', '-s', 'tests', '-v')
        WorkingDirectory = (Get-Location).Path
        Wait = $true
        PassThru = $true
        NoNewWindow = $true
        RedirectStandardOutput = $stdoutPath
        RedirectStandardError = $stderrPath
    }
    $process = Start-Process @startInfo

    foreach ($logPath in @($stdoutPath, $stderrPath)) {
        if (Test-Path -LiteralPath $logPath) {
            Get-Content -LiteralPath $logPath | ForEach-Object { [Console]::Out.WriteLine($_) }
        }
    }

    if ($process.ExitCode -ne 0) {
        [Console]::Error.WriteLine("unittest failed with exit code $($process.ExitCode).")
        exit $process.ExitCode
    }
    exit 0
}
finally {
    Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
}
