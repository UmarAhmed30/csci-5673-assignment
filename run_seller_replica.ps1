param([int]$n)
# Always resolve relative to the script's location
Set-Location $PSScriptRoot
$envFile = "env.seller.replica.$n"
Get-Content $envFile | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}
Set-Location db_layer\seller
python seller.py

# Usage:
# .\run_seller_replica.ps1 <replica_number>
