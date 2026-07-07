param(
    [Parameter(Mandatory=$true)][string]$StaticDir,
    [Parameter(Mandatory=$true)][string]$OutFile
)
$ErrorActionPreference = "Stop"
function Write-RawString([string]$Name, [string]$Path) {
    $Text = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
    $Token = $Name
    $Needle = ')' + $Token + '"'
    while ($Text.Contains($Needle)) {
        $Token = $Token + '_X'
        $Needle = ')' + $Token + '"'
    }
    return 'static const char ' + $Name + '[] = R"' + $Token + '(' + $Text + ')' + $Token + '";' + "`n"
}
$OutDir = Split-Path -Parent $OutFile
New-Item -ItemType Directory -Force $OutDir | Out-Null
$Body = "#pragma once`n"
$Body += Write-RawString "INDEX_HTML" (Join-Path $StaticDir "index.html")
$Body += Write-RawString "STYLE_CSS" (Join-Path $StaticDir "style.css")
$Body += Write-RawString "APP_JS" (Join-Path $StaticDir "app.js")
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($OutFile, $Body, $Utf8NoBom)
