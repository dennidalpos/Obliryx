#requires -Version 5.1
<#
.SYNOPSIS
Avvia Obliryx con menu interattivi.
.EXAMPLE
.\Avvia-Obliryx.ps1
.EXAMPLE
.\Avvia-Obliryx.ps1 -DatabasePath 'D:\Dati personali\obliryx.sqlite3'
#>
[CmdletBinding()]
param(
    [string]$DatabasePath,
    [string]$PythonPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$script:ProjectDirectory = $PSScriptRoot
$script:Database = $DatabasePath
$script:ManagedPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$script:PythonExecutable = $PythonPath
if (!$script:PythonExecutable) { $script:PythonExecutable = $script:ManagedPython }

function Select-MenuItem {
    param([string]$Title, [object[]]$Items, [string]$BackLabel = 'Indietro')
    while ($true) {
        Write-Host "`n$Title" -ForegroundColor Cyan
        for ($index = 0; $index -lt $Items.Count; $index++) {
            Write-Host ('  {0}. {1}' -f ($index + 1), $Items[$index].Label)
        }
        Write-Host "  0. $BackLabel"
        $answer = Read-Host 'Scelta'
        if ($answer -eq '0') { return $null }
        $number = 0
        if ([int]::TryParse($answer, [ref]$number) -and $number -ge 1 -and $number -le $Items.Count) {
            return $Items[$number - 1]
        }
        Write-Host 'Scegli uno dei numeri indicati.' -ForegroundColor Yellow
    }
}

function Read-OperationField {
    param([hashtable]$Field)
    if ($Field.ContainsKey('Choices')) {
        $selected = Select-MenuItem -Title $Field.Prompt -Items $Field.Choices -BackLabel 'Annulla operazione'
        if ($null -eq $selected) { throw [OperationCanceledException]::new() }
        return $selected.Value
    }
    while ($true) {
        $label = $Field.Prompt
        if ($Field.ContainsKey('Default')) { $label += ' [Invio = ' + $Field.Default + ']' }
        elseif ($Field.ContainsKey('Optional')) { $label += ' [facoltativo]' }
        $value = (Read-Host $label).Trim()
        if ($value -eq 'q') { throw [OperationCanceledException]::new() }
        if (!$value -and $Field.ContainsKey('Default')) { $value = [string]$Field.Default }
        if (!$value -and $Field.ContainsKey('Optional')) { return $null }
        if (!$value) { Write-Host 'Inserisci un valore oppure q per annullare.'; continue }
        switch ($Field.Kind) {
            'Path' {
                $value = $value.Trim('"')
                if (Test-Path -LiteralPath $value -PathType $Field.PathType) {
                    return (Resolve-Path -LiteralPath $value).ProviderPath
                }
                Write-Host 'Il percorso indicato non esiste o ha un tipo diverso da quello richiesto.' -ForegroundColor Yellow
            }
            'Guid' {
                $id = [guid]::Empty
                if ([guid]::TryParse($value, [ref]$id)) { return $id.ToString() }
                Write-Host 'Copia un ID completo dal risultato di Elenca riscontri.' -ForegroundColor Yellow
            }
            'Integer' {
                $number = 0
                if ([int]::TryParse($value, [ref]$number) -and $number -ge $Field.Min -and $number -le $Field.Max) {
                    return [string]$number
                }
                Write-Host ('Inserisci un numero tra {0} e {1}.' -f $Field.Min, $Field.Max) -ForegroundColor Yellow
            }
            default { return $value }
        }
    }
}

function Invoke-Obliryx {
    param([string[]]$CommandArguments)
    $invocation = @('-m', 'obliryx')
    if ($script:Database) { $invocation += @('--db', $script:Database) }
    $invocation += $CommandArguments
    # Quote for the Windows executable parser, without another shell or stream redirection.
    # Windows PowerShell 5.1's native-call operator can otherwise drop embedded quotes.
    $encoded = foreach ($argument in $invocation) {
        $argument = [regex]::Replace($argument, '(\\*)"', '$1$1\"')
        $argument = [regex]::Replace($argument, '(\\+)$', '$1$1')
        '"' + $argument + '"'
    }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $script:PythonExecutable
    $start.Arguments = $encoded -join ' '
    $start.WorkingDirectory = (Get-Location).ProviderPath
    $start.UseShellExecute = $false
    # Inherit the console so that Python can read secret prompts and confirmations.
    $previousUtf8 = $env:PYTHONUTF8
    $process = $null
    try {
        $env:PYTHONUTF8 = '1'
        $process = [Diagnostics.Process]::Start($start)
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            Write-Host ('Operazione terminata con codice {0}. Consulta il messaggio di Obliryx.' -f $process.ExitCode) -ForegroundColor Yellow
        }
    }
    finally {
        if ($process) { $process.Dispose() }
        $env:PYTHONUTF8 = $previousUtf8
    }
}

function Test-ObliryxEnvironment {
    if (!(Test-Path -LiteralPath $script:PythonExecutable -PathType Leaf)) { return $false }
    try {
        & $script:PythonExecutable -c 'import sys, obliryx.cli; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>$null
        return $LASTEXITCODE -eq 0
    }
    catch { return $false }
}

function Install-ObliryxEnvironment {
    if (!(Test-Path -LiteralPath $script:ManagedPython -PathType Leaf)) {
        $python = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (!$python) { throw 'Installa Python 3.11 o successivo e rendi disponibile il comando python.' }
        & $python.Source -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
        if ($LASTEXITCODE -ne 0) { throw 'Serve Python 3.11 o successivo.' }
        & $python.Source -m venv (Join-Path $script:ProjectDirectory '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Creazione dell''ambiente Python non riuscita.' }
    }
    & $script:ManagedPython -m pip --cache-dir (Join-Path $script:ProjectDirectory '.local\pip-cache') install -e $script:ProjectDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Installazione di Obliryx non riuscita.' }
    $script:PythonExecutable = $script:ManagedPython
    if (!(Test-ObliryxEnvironment)) { throw 'Ambiente Python non pronto.' }
    Write-Host 'Obliryx pronto.' -ForegroundColor Green
}

function Set-ArchivePath {
    Write-Host 'Il percorso scelto vale per questa sessione. Invio usa l''archivio predefinito di Obliryx.'
    $value = (Read-Host 'Percorso del database SQLite').Trim().Trim('"')
    if ($value -eq 'q') { throw [OperationCanceledException]::new() }
    if ($value) { $script:Database = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($value) }
    else { $script:Database = $null }
}

$categories = @('email', 'nome', 'username', 'telefono', 'indirizzo', 'documento', 'finanziari', 'salute') |
    ForEach-Object { @{Label = $_; Value = $_} }
$auth = @(
    @{Label = 'Password per app del provider'; Value = 'app-password'},
    @{Label = 'Token OAuth IMAP gia ottenuto'; Value = 'xoauth2'}
)
$script:Fields = @{
    Id = @{Prompt = 'ID del riscontro'; Kind = 'Guid'}
    Route = @{Prompt = 'Numero del canale, visibile in Mostra riscontro'; Kind = 'Integer'; Min = 1; Max = [int]::MaxValue}
    LocalSource = @{Prompt = 'File .eml, cartella .eml o esportazione .mbox'; Kind = 'Path'; PathType = 'Any'}
    Eml = @{Prompt = 'File .eml o cartella con file .eml'; Kind = 'Path'; PathType = 'Any'}
    File = @{Prompt = 'File .mbox'; Kind = 'Path'; PathType = 'Leaf'}
    Original = @{Prompt = 'File originale .eml o archivio .mbox'; Kind = 'Path'; PathType = 'Leaf'}
    Directory = @{Prompt = 'Cartella con file .eml'; Kind = 'Path'; PathType = 'Container'}
    Category = @{Prompt = 'Categoria del tuo dato'; Choices = $categories}
    Host = @{Prompt = 'Server IMAP ufficiale del provider'; Kind = 'Text'}
    Mailbox = @{Prompt = 'Cartella IMAP'; Kind = 'Text'; Default = 'INBOX'; Flag = '--mailbox'}
    Limit = @{Prompt = 'Numero massimo di messaggi recenti'; Kind = 'Integer'; Min = 1; Max = 500; Default = 50; Flag = '--limit'}
    Interval = @{Prompt = 'Intervallo di controllo in secondi'; Kind = 'Integer'; Min = 1; Max = 3600; Default = 30; Flag = '--interval'}
    Auth = @{Prompt = 'Metodo di accesso IMAP'; Choices = $auth; Flag = '--auth'}
    Source = @{Prompt = 'Numero della fonte IMAP se ne esiste piu di una'; Kind = 'Integer'; Min = 1; Max = [int]::MaxValue; Optional = $true; Flag = '--source'}
    Match = @{Prompt = 'Cercare anche un tuo dato nel contenuto?'; Flag = '--match'; Choices = @(@{Label = 'Solo analisi di marketing e mailing list'; Value = $null}) + $categories}
    BreachMethod = @{Prompt = 'Metodo di ricerca HIBP'; Flag = '--method'; Choices = @(
        @{Label = 'Indirizzo completo (piano compatibile)'; Value = 'diretto'},
        @{Label = 'Prefisso hash (piano Pro o High RPM)'; Value = 'prefisso'}
    )}
    Review = @{Prompt = 'Stato dell''iscrizione'; Choices = @(
        @{Label = 'Da verificare'; Value = 'da_verificare'},
        @{Label = 'Riconosciuta'; Value = 'riconosciuta'},
        @{Label = 'Non riconosciuta'; Value = 'non_riconosciuta'}
    )}
    Outcome = @{Prompt = 'Esito osservato'; Choices = @(
        @{Label = 'Richiesta inviata'; Value = 'inviata'},
        @{Label = 'Rimozione dichiarata dal titolare'; Value = 'rimozione_dichiarata'},
        @{Label = 'Dato non osservato alla fonte'; Value = 'dato_non_osservato'},
        @{Label = 'Dato ricomparso'; Value = 'ricomparsa'},
        @{Label = 'Non verificabile'; Value = 'non_verificabile'}
    )}
    DraftAction = @{Prompt = 'Tipo di richiesta'; Flag = '--action'; Choices = @(
        @{Label = 'Opposizione al marketing'; Value = 'opposizione'},
        @{Label = 'Cancellazione dei dati'; Value = 'cancellazione'},
        @{Label = 'Accesso e origine dei dati'; Value = 'accesso'}
    )}
    Compose = @{Prompt = 'Aprire la bozza nel client di posta?'; Flag = '--compose'; Switch = $true; Choices = @(
        @{Label = 'Mostra soltanto la bozza'; Value = $null},
        @{Label = 'Apri nel client di posta'; Value = 'yes'}
    )}
}

$menus = @(
    @{Label = 'Importa e monitora la posta'; Items = @(
        @{Label = 'Importa email .eml'; Command = 'import-eml'; Fields = @('Eml')},
        @{Label = 'Importa una casella esportata .mbox'; Command = 'import-mbox'; Fields = @('File')},
        @{Label = 'Leggi una casella IMAP'; Command = 'import-imap'; Fields = @('Host', 'Mailbox', 'Limit', 'Auth', 'Match')},
        @{Label = 'Monitora una cartella .eml (Ctrl+C termina il monitoraggio)'; Command = 'watch-eml'; Fields = @('Directory', 'Interval')},
        @{Label = 'Cerca un tuo dato nella posta locale'; Command = 'scan-mail'; Fields = @('LocalSource', 'Category')}
    )},
    @{Label = 'Cerca e verifica esposizioni'; Items = @(
        @{Label = 'Ricerca Web con Brave'; Command = 'search-web'; Fields = @()},
        @{Label = 'Verifica violazioni con HIBP'; Command = 'check-breach'; Fields = @('BreachMethod')},
        @{Label = 'Verifica un tuo dato su una pagina Web'; Command = 'check-page'; Fields = @('Category')},
        @{Label = 'Ricontrolla una pagina gia registrata'; Command = 'recheck-page'; Fields = @('Id')},
        @{Label = 'Registra un riscontro manualmente'; Command = 'record'; Fields = @()}
    )},
    @{Label = 'Consulta e revisiona i riscontri'; Items = @(
        @{Label = 'Elenca riscontri e ID'; Command = 'list'; Fields = @()},
        @{Label = 'Riepilogo delle campagne'; Command = 'campaigns'; Fields = @()},
        @{Label = 'Mostra un riscontro, i canali e lo storico'; Command = 'show'; Fields = @('Id')},
        @{Label = 'Revisiona un''iscrizione'; Command = 'review'; Fields = @('Id', 'Review')},
        @{Label = 'Aggiungi prove e contatto privacy'; Command = 'document'; Fields = @('Id')},
        @{Label = 'Documenta chi e il titolare'; Command = 'identify'; Fields = @('Id')},
        @{Label = 'Registra un esito'; Command = 'outcome'; Fields = @('Id', 'Outcome')}
    )},
    @{Label = 'Prepara richieste e disiscrizioni'; Items = @(
        @{Label = 'Prepara una richiesta privacy'; Command = 'draft'; Fields = @('Id', 'DraftAction', 'Compose')},
        @{Label = 'Prepara la mail indicata dal canale di disiscrizione'; Command = 'draft'; Fields = @('Id', 'Route', 'Compose'); RouteFlag = $true},
        @{Label = 'Cerca canali privacy per un riscontro'; Command = 'find-routes'; Fields = @('Id')},
        @{Label = 'Conferma un canale verificato manualmente'; Command = 'confirm-route'; Fields = @('Id', 'Route')},
        @{Label = 'Apri il canale nel browser'; Command = 'open-route'; Fields = @('Id', 'Route')},
        @{Label = 'Disiscrizione one-click da file originale'; Command = 'unsubscribe'; Fields = @('Id', 'Original')},
        @{Label = 'Disiscrizione one-click da messaggio IMAP'; Command = 'unsubscribe-imap'; Fields = @('Id', 'Source', 'Auth')},
        @{Label = 'Compila un modulo semplice di disiscrizione'; Command = 'form-unsubscribe'; Fields = @('Id', 'Route')}
    )},
    @{Label = 'Archivio e ambiente Python'; Items = @(
        @{Label = 'Scegli l''archivio per questa sessione'; Action = 'Database'},
        @{Label = 'Installa o aggiorna l''ambiente locale .venv'; Action = 'Install'},
        @{Label = 'Mostra la guida dei comandi'; Command = '--help'; Fields = @()}
    )}
)

function Invoke-MenuOperation {
    param([hashtable]$Operation)
    if ($Operation.ContainsKey('Action')) {
        switch ($Operation.Action) {
            'Database' { Set-ArchivePath }
            'Install' { Install-ObliryxEnvironment }
        }
        return
    }
    $commandArguments = @($Operation.Command)
    foreach ($name in $Operation.Fields) {
        $field = $script:Fields[$name]
        $value = Read-OperationField $field
        if ($null -eq $value) { continue }
        if ($Operation.ContainsKey('RouteFlag') -and $name -eq 'Route') { $commandArguments += '--route' }
        elseif ($field.ContainsKey('Flag')) { $commandArguments += $field.Flag }
        if (!$field.ContainsKey('Switch')) { $commandArguments += $value }
    }
    Invoke-Obliryx $commandArguments
}

function Start-ObliryxMenu {
    if (!(Test-ObliryxEnvironment)) {
        $install = Select-MenuItem -Title 'Prepara Obliryx' -BackLabel 'Esci' -Items @(
            @{Label = 'Crea .venv e installa le dipendenze con pip'}
        )
        if ($null -eq $install) { return }
        Install-ObliryxEnvironment
    }
    Write-Host 'Scegli un numero; 0 torna indietro. Durante l''inserimento dei parametri, q annulla l''operazione.'
    while ($true) {
        $archiveLabel = 'predefinito di Obliryx'
        if ($script:Database) { $archiveLabel = $script:Database }
        Write-Host "`nArchivio: $archiveLabel"
        $group = Select-MenuItem -Title 'Obliryx' -Items $menus -BackLabel 'Esci'
        if ($null -eq $group) { return }
        $operation = Select-MenuItem -Title $group.Label -Items $group.Items
        if ($null -eq $operation) { continue }
        try { Invoke-MenuOperation $operation }
        catch [OperationCanceledException] { Write-Host 'Operazione annullata.' }
        catch { Write-Host $_.Exception.Message -ForegroundColor Red }
        [void](Read-Host 'Premi Invio per tornare al menu')
    }
}

# Dot-sourcing makes the menu functions available for verification and interactive reuse.
if ($MyInvocation.InvocationName -ne '.') {
    # Resolve caller-supplied paths before switching to the project's directory.
    if ($script:Database) { $script:Database = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($script:Database) }
    if ($PythonPath) { $script:PythonExecutable = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($PythonPath) }
    Push-Location -LiteralPath $script:ProjectDirectory
    try { Start-ObliryxMenu }
    finally { Pop-Location }
}
