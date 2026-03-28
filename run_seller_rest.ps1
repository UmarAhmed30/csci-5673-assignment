param([int]$n)
Set-Location $PSScriptRoot
$envFile = "env.seller.rest.$n"
Get-Content $envFile | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}
python server\seller\seller_rest.py

# Usage:
# .\run_seller_rest.ps1 <replica_number>   (0-3)
