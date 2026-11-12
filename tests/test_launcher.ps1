#requires -Version 5.1
param([string]$PythonPath = (Get-Command python -CommandType Application | Select-Object -First 1).Source)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'Avvia-Obliryx.ps1') -PythonPath $PythonPath
$fixture = Join-Path $root ('.local\launcher-tests\' + [guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($fixture)
$mailFile = Join-Path $fixture 'posta [test] & $().eml'
[IO.File]::WriteAllText($mailFile, 'Synthetic launcher fixture')
$id = 'd195bd92-5ac6-4ba7-9305-55795c7b2637'
$script:Calls = New-Object 'Collections.Generic.List[object]'

function Assert-True($Condition, [string]$Message) {
    if (!$Condition) { throw $Message }
}
function Set-Answers([string[]]$Answers) {
    $script:Answers = New-Object 'Collections.Generic.Queue[string]'
    foreach ($answer in $Answers) { $script:Answers.Enqueue($answer) }
}
function Read-Host([string]$Prompt) {
    if (!$script:Answers.Count) { throw "Unexpected prompt: $Prompt" }
    return $script:Answers.Dequeue()
}

& {
    function Invoke-Obliryx([string[]]$CommandArguments) { $script:Calls.Add($CommandArguments) }
    foreach ($lastChoice in @($false, $true)) {
        foreach ($group in $menus) {
            foreach ($operation in $group.Items) {
                if ($operation.ContainsKey('Action')) { continue }
                $answers = foreach ($name in $operation.Fields) {
                    $field = $script:Fields[$name]
                    if ($field.ContainsKey('Choices')) {
                        if ($lastChoice) { [string]$field.Choices.Count } else { '1' }
                    }
                    elseif ($field.ContainsKey('Optional')) { if ($lastChoice) { '2' } else { '' } }
                    elseif ($field.ContainsKey('Default')) { '' }
                    else {
                        switch ($field.Kind) {
                            'Guid' { $id }
                            'Integer' { '1' }
                            'Path' { if ($field.PathType -eq 'Container') { $fixture } else { $mailFile } }
                            default { 'imap.example.test' }
                        }
                    }
                }
                Set-Answers @($answers)
                Invoke-MenuOperation $operation
                Assert-True ($script:Answers.Count -eq 0) 'Not all operation prompts were consumed'
            }
        }
    }
    $before = $script:Calls.Count
    Set-Answers @('q')
    try { Invoke-MenuOperation $menus[2].Items[2]; throw 'Cancellation did not stop the operation' }
    catch [OperationCanceledException] { }
    Assert-True ($script:Calls.Count -eq $before) 'Cancelled operation reached Python'
}

Set-Answers @('invalid', '0', '501', '')
Assert-True ((Read-OperationField $script:Fields.Limit) -eq '50') 'Integer validation/default failed'
Set-Answers @('invalid', $id)
Assert-True ((Read-OperationField $script:Fields.Id) -eq $id) 'ID validation failed'
Set-Answers @('missing-file', ('"' + $mailFile + '"'))
Assert-True ((Read-OperationField $script:Fields.Eml) -eq $mailFile) 'Literal path validation failed'
Set-Answers @('999', '0')
Assert-True ($null -eq (Select-MenuItem 'Test' @(@{Label = 'One'}))) 'Menu back option failed'
$script:Database = 'unchanged.sqlite3'
Set-Answers @('q')
try { Set-ArchivePath; throw 'Archive selection did not cancel' }
catch [OperationCanceledException] { }
Assert-True ($script:Database -eq 'unchanged.sqlite3') 'Cancellation changed the archive'
Set-Answers @('')
Set-ArchivePath
Assert-True ($null -eq $script:Database) 'Default archive selection failed'

# Parse every generated command with the real CLI, without executing any operation.
$casesFile = Join-Path $fixture 'commands.json'
[IO.File]::WriteAllText($casesFile, (ConvertTo-Json -InputObject $script:Calls.ToArray() -Depth 5))
$parserTest = Join-Path $fixture 'parse_commands.py'
[IO.File]::WriteAllText($parserTest, @'
import json, sys
from obliryx.cli import parser
with open(sys.argv[1], encoding="utf-8") as source:
    cases = json.load(source)
for case in cases:
    if case != ["--help"]:
        parser().parse_args(case)
print(str(len(cases)) + " menu command variants parsed")
'@)
& $PythonPath $parserTest $casesFile
Assert-True ($LASTEXITCODE -eq 0) 'Generated command rejected by CLI parser'
$routeDrafts = @($script:Calls | Where-Object { $_[0] -eq 'draft' -and $_ -contains '--route' })
Assert-True ($routeDrafts.Count -eq 2) 'Draft route must be a named argument'
Assert-True (@($script:Calls | Where-Object { $_ -contains '--compose' }).Count -eq 2) 'Compose switch missing'

# A synthetic Python module records the actual Windows argv received by the child.
$module = Join-Path $fixture 'obliryx'
[void][IO.Directory]::CreateDirectory($module)
[IO.File]::WriteAllText((Join-Path $module '__init__.py'), '')
[IO.File]::WriteAllText((Join-Path $module '__main__.py'), @'
import json, os, sys
with open(os.environ["OBLIRYX_LAUNCHER_TEST_OUTPUT"], "w", encoding="utf-8") as out:
    json.dump(sys.argv[1:], out)
'@)
$outputFile = Join-Path $fixture 'received.json'
$previousOutput = $env:OBLIRYX_LAUNCHER_TEST_OUTPUT
$previousUtf8 = $env:PYTHONUTF8
$env:OBLIRYX_LAUNCHER_TEST_OUTPUT = $outputFile
$script:Database = Join-Path $fixture 'archivio personale [test].sqlite3'
$arguments = @('import-imap', 'imap.example.test', '--mailbox', 'a"b c"d & $()', '--extra', 'C:\folder space\', '', ('Unicode: citta' + [char]0xE0))
Push-Location -LiteralPath $fixture
try {
    Invoke-Obliryx $arguments
    $received = Get-Content -LiteralPath $outputFile -Raw | ConvertFrom-Json
    $expected = @('--db', $script:Database) + $arguments
    Assert-True ($received.Count -eq $expected.Count) 'Native argument count changed'
    for ($index = 0; $index -lt $expected.Count; $index++) {
        Assert-True ($received[$index] -ceq $expected[$index]) "Native argument $index changed"
    }
    Assert-True ($env:PYTHONUTF8 -ceq $previousUtf8) 'Python environment variable was not restored'
}
finally {
    Pop-Location
    $env:OBLIRYX_LAUNCHER_TEST_OUTPUT = $previousOutput
    $env:PYTHONUTF8 = $previousUtf8
}
$script:PythonExecutable = Join-Path $fixture 'missing-python.exe'
Assert-True (!(Test-ObliryxEnvironment)) 'Missing Python reported as ready'
$script:PythonExecutable = $PythonPath
Assert-True (Test-ObliryxEnvironment) 'Installed environment reported as unavailable'
Write-Host 'PASS: menu commands, validation, cancellation and native arguments' -ForegroundColor Green
