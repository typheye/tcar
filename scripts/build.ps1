param([switch]$Install)
$arguments = @('build')
if ($Install) { $arguments += '--install' }
& "$PSScriptRoot/pc.cmd" @arguments
exit $LASTEXITCODE
