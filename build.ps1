param(
    [string]$Python = "",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$previousLocation = Get-Location
$oldPipCache = $env:PIP_CACHE_DIR
$oldPyinstallerCache = $env:PYINSTALLER_CONFIG_DIR
$oldTclLibrary = $env:TCL_LIBRARY
$oldTkLibrary = $env:TK_LIBRARY
$oldTemp = $env:TEMP
$oldTmp = $env:TMP

function Invoke-CheckedPython {
    param([string]$Interpreter, [string[]]$PythonArgs)
    & $Interpreter @PythonArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed (exit $LASTEXITCODE): $($PythonArgs -join ' ')"
    }
}

try {
    Set-Location -LiteralPath $projectRoot
    $toolsRoot = Join-Path $projectRoot ".build-tools"
    New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
    $env:PIP_CACHE_DIR = Join-Path $toolsRoot "pip-cache"
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $toolsRoot "pyinstaller-cache"
    $venvPython = Join-Path $projectRoot ".venv-build/Scripts/python.exe"

    if (-not (Test-Path -LiteralPath $venvPython)) {
        if (-not $Python) {
            $candidates = @()
            $launcher = Get-Command py -ErrorAction SilentlyContinue
            if ($launcher) {
                $launched = & $launcher.Source -3 -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0) { $candidates += $launched }
            }
            $command = Get-Command python -ErrorAction SilentlyContinue
            if ($command -and $command.Source -notlike "*WindowsApps*") {
                $candidates += $command.Source
            }
            $uvPythonRoot = Join-Path $env:APPDATA "uv/python"
            if (Test-Path -LiteralPath $uvPythonRoot) {
                $candidates += Get-ChildItem -LiteralPath $uvPythonRoot -Directory |
                    Where-Object Name -Match '^cpython-3\.(12|13|14)\..*windows-x86_64' |
                    Sort-Object Name -Descending |
                    ForEach-Object { Join-Path $_.FullName "python.exe" }
            }
            $Python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        }
        if (-not $Python) {
            throw 'Python 3.12-3.14 x64 is required to BUILD. Install Python with Tcl/Tk, then rerun build.ps1 -Python "C:\path\python.exe". End users do not need Python.'
        }
        Invoke-CheckedPython $Python @("-c", "import sys, struct; assert (3,12) <= sys.version_info[:2] < (3,15), 'Use Python 3.12-3.14'; assert struct.calcsize('P') == 8, 'Use 64-bit Python'")
        Invoke-CheckedPython $Python @("-m", "venv", (Join-Path $projectRoot ".venv-build"))
    }

    # Stage Tcl/Tk inside the workspace. This also supports Python distributions
    # whose Tcl installation path is not discoverable automatically.
    Invoke-CheckedPython $venvPython @("tools/prepare_tk.py")
    $stagedTcl = Join-Path $toolsRoot "tcl/tcl8.6"
    $stagedTk = Join-Path $toolsRoot "tcl/tk8.6"
    if ((Test-Path -LiteralPath $stagedTcl) -and (Test-Path -LiteralPath $stagedTk)) {
        $env:TCL_LIBRARY = $stagedTcl
        $env:TK_LIBRARY = $stagedTk
    }
    # Fail early if this Python installation cannot create a desktop window.
    Invoke-CheckedPython $venvPython @("-c", "import tkinter as tk; w=tk.Tk(); w.withdraw(); w.update(); w.destroy()")
    if (-not $SkipInstall) {
        Invoke-CheckedPython $venvPython @("-m", "pip", "install", "--upgrade", "pip")
        Invoke-CheckedPython $venvPython @("-m", "pip", "install", "-r", "requirements-build.txt")
    }
    Invoke-CheckedPython $venvPython @("-m", "unittest", "discover", "-s", "tests", "-v")
    Invoke-CheckedPython $venvPython @("tools/third_party_notices.py")
    Invoke-CheckedPython $venvPython @("app.py", "--self-test", "--fixtures", "markitdown-main/packages/markitdown/tests/test_files", "--report", ".build-tools/source-smoke.json")
    $runtimeRegressionArgs = @()
    $conflictingRuntime = Join-Path $env:ProgramFiles "TortoiseGit/bin/MSVCP140.dll"
    if (Test-Path -LiteralPath $conflictingRuntime) {
        $runtimeRegressionArgs = @("--conflicting-runtime", $conflictingRuntime)
    }
    Invoke-CheckedPython $venvPython (@("app.py", "--gui-self-test", "--fixtures", "markitdown-main/packages/markitdown/tests/test_files", "--report", ".build-tools/source-gui-smoke.json") + $runtimeRegressionArgs)
    # Keep the existing release intact until the rebuilt EXE passes all checks.
    $stageDist = Join-Path $toolsRoot "release"
    Invoke-CheckedPython $venvPython @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $stageDist, "--workpath", ".build-tools/pyinstaller", "MDConverter.spec")

    $exe = Join-Path $stageDist "MD Converter.exe"
    if (-not (Test-Path -LiteralPath $exe)) { throw "Build did not produce $exe" }
    Invoke-CheckedPython $venvPython @("tools/check_exe_icon.py", $exe)
    # Launch from a separate working directory to catch source-tree dependencies.
    $smokeWork = Join-Path $toolsRoot "portable-smoke"
    New-Item -ItemType Directory -Force -Path $smokeWork | Out-Null
    # Use a writable, predictable scratch directory for extracted Tcl resources
    # during validation, including when the build runs in a restricted sandbox.
    $runtimeTemp = Join-Path $toolsRoot "runtime-temp"
    New-Item -ItemType Directory -Force -Path $runtimeTemp | Out-Null
    $env:TEMP = $runtimeTemp
    $env:TMP = $runtimeTemp
    $report = Join-Path $toolsRoot "exe-smoke.json"
    $fixtures = Join-Path $projectRoot "markitdown-main/packages/markitdown/tests/test_files"
    $arguments = @("--self-test", "--fixtures", ('"' + $fixtures + '"'), "--report", ('"' + $report + '"'))
    $process = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $smokeWork -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "EXE smoke test failed. See $report" }
    if (-not (Test-Path -LiteralPath $report)) { throw "EXE did not write its smoke-test report." }
    $smoke = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
    if (-not $smoke.passed) { throw "EXE smoke test failed. See $report" }
    $guiReport = Join-Path $toolsRoot "exe-gui-smoke.json"
    $guiArguments = @("--gui-self-test", "--fixtures", ('"' + $fixtures + '"'), "--report", ('"' + $guiReport + '"'))
    if ($runtimeRegressionArgs.Count) {
        $guiArguments += @("--conflicting-runtime", ('"' + $conflictingRuntime + '"'))
    }
    $guiProcess = Start-Process -FilePath $exe -ArgumentList $guiArguments -WorkingDirectory $smokeWork -WindowStyle Hidden -PassThru
    if (-not $guiProcess.WaitForExit(180000)) {
        $guiProcess.Kill()
        throw "EXE GUI regression test timed out. See $guiReport"
    }
    if ($guiProcess.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $guiReport)) {
        throw "EXE GUI regression test failed. See $guiReport"
    }
    $guiSmoke = Get-Content -LiteralPath $guiReport -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $guiSmoke.passed) { throw "EXE GUI regression test failed. See $guiReport" }
    $delivery = Join-Path $projectRoot "dist"
    New-Item -ItemType Directory -Force -Path $delivery | Out-Null
    try {
        Copy-Item -LiteralPath $exe -Destination (Join-Path $delivery "MD Converter.exe") -Force
    }
    catch [System.IO.IOException] {
        # A running previous release must not be terminated just to replace it.
        $nativeError = $_.Exception.HResult -band 0xFFFF
        if ($nativeError -notin @(32,33)) { throw }
        $delivery = Join-Path $projectRoot "release"
        New-Item -ItemType Directory -Force -Path $delivery | Out-Null
        Copy-Item -LiteralPath $exe -Destination (Join-Path $delivery "MD Converter.exe") -Force
        Write-Host "The previous EXE is running. The verified update is available in release/MD Converter.exe."
    }
    $exe = Join-Path $delivery "MD Converter.exe"
    $artifacts = @(Get-ChildItem -LiteralPath $delivery -Force)
    if ($artifacts.Count -ne 1 -or $artifacts[0].Name -ne "MD Converter.exe") {
        throw "dist contains extra files. Move them elsewhere so the delivery folder contains only MD Converter.exe."
    }
    & $venvPython -m pip freeze | Set-Content -LiteralPath (Join-Path $toolsRoot "requirements-resolved.txt") -Encoding UTF8
    Write-Host "Build and portable conversion checks passed: $exe"
    Write-Host "Only this EXE needs to be copied to the user's Windows x64 computer."
}
finally {
    $env:PIP_CACHE_DIR = $oldPipCache
    $env:PYINSTALLER_CONFIG_DIR = $oldPyinstallerCache
    $env:TCL_LIBRARY = $oldTclLibrary
    $env:TK_LIBRARY = $oldTkLibrary
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    Set-Location -LiteralPath $previousLocation
}
