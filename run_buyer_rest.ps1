param([int]$n)
Set-Location $PSScriptRoot
$envFile = "env.buyer.rest.$n"
Get-Content $envFile | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}
python server\buyer\buyer_rest.py

# Usage:
# .\run_buyer_rest.ps1 <replica_number>   (0-3)
