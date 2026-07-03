[CmdletBinding()]
param(
  [string]$HunyuanRoot,
  [string]$DefaultOutput,
  [switch]$Gui,
  [switch]$SkipCodexInstall,
  [switch]$WriteLocalMcp
)

$ErrorActionPreference = "Stop"

function Select-Folder {
  param([string]$Description)

  Add-Type -AssemblyName System.Windows.Forms
  $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
  $dialog.Description = $Description
  $dialog.ShowNewFolderButton = $false
  $result = $dialog.ShowDialog()
  if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    return $dialog.SelectedPath
  }
  return $null
}

function Assert-HunyuanRoot {
  param([string]$PathValue)

  if (-not $PathValue) {
    throw "Pass -HunyuanRoot or run with -Gui."
  }
  $resolved = (Resolve-Path -LiteralPath $PathValue).Path
  $python = Join-Path $resolved "python_standalone\python.exe"
  $api = Join-Path $resolved "Hunyuan3D-2\api_server.py"
  if (-not (Test-Path -LiteralPath $python)) {
    throw "Hunyuan portable Python was not found at: $python"
  }
  if (-not (Test-Path -LiteralPath $api)) {
    throw "Hunyuan3D-2 API server was not found at: $api"
  }
  return $resolved
}

function Get-PythonCommand {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return @{ Command = $python.Source; Args = @() }
  }
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return @{ Command = $py.Source; Args = @("-3") }
  }
  throw "Python was not found on PATH. Install Python 3 or add it to PATH, then rerun this installer."
}

function Get-CodexCommand {
  $bundledRoot = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin"
  if (Test-Path -LiteralPath $bundledRoot) {
    $bundled = Get-ChildItem -LiteralPath $bundledRoot -Recurse -Filter "codex.exe" -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
    if ($bundled) {
      return $bundled.FullName
    }
  }

  $codex = Get-Command codex -ErrorAction SilentlyContinue
  if ($codex -and ($codex.Source -notmatch "\\WindowsApps\\")) {
    return $codex.Source
  }
  if ($codex) {
    return $codex.Source
  }
  return $null
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Join-Path $repoRoot "plugins\hunyuan-glb-generator"
$configureScript = Join-Path $pluginRoot "scripts\configure_plugin.py"

if (-not (Test-Path -LiteralPath $configureScript)) {
  throw "Could not find plugin configure script at: $configureScript"
}

if ($Gui -and -not $HunyuanRoot) {
  $HunyuanRoot = Select-Folder "Select the Hunyuan3D portable root that contains python_standalone and Hunyuan3D-2"
}

$HunyuanRoot = Assert-HunyuanRoot $HunyuanRoot

if ($Gui -and -not $DefaultOutput) {
  $DefaultOutput = Select-Folder "Optional: select a default output folder for generated GLBs. Press Cancel to skip."
}

if ($DefaultOutput) {
  $DefaultOutput = (Resolve-Path -LiteralPath $DefaultOutput).Path
}

$pythonInfo = Get-PythonCommand
$configureArgs = @($configureScript, "--hunyuan-root", $HunyuanRoot)
if ($DefaultOutput) {
  $configureArgs += @("--default-output", $DefaultOutput)
}
if ($WriteLocalMcp) {
  $configureArgs += "--write-local-mcp"
}

Write-Host "Configuring Hunyuan GLB Generator..."
& $pythonInfo.Command @($pythonInfo.Args + $configureArgs)
if ($LASTEXITCODE -ne 0) {
  throw "Plugin configuration failed."
}

if (-not $SkipCodexInstall) {
  $codex = Get-CodexCommand
  if ($codex) {
    Write-Host "Registering local Codex marketplace..."
    & $codex "plugin" "marketplace" "add" $repoRoot
    if ($LASTEXITCODE -ne 0) {
      Write-Warning "Marketplace registration returned a non-zero exit code. It may already be registered."
    }

    Write-Host "Installing Codex plugin..."
    & $codex "plugin" "add" "hunyuan-glb-generator@hunyuan-glb-generator-marketplace"
    if ($LASTEXITCODE -ne 0) {
      Write-Warning "Codex plugin install returned a non-zero exit code. Open Codex Plugins and install it from the Hunyuan GLB Generator marketplace if needed."
    }
  } else {
    Write-Warning "Codex CLI was not found on PATH. The plugin was configured, but marketplace/plugin install was skipped."
  }
}

Write-Host ""
Write-Host "Done."
Write-Host "Start a new Codex thread, then ask Codex to use Hunyuan GLB Generator."
