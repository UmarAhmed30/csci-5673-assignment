param([int]$n)
# Always resolve relative to the script's location
Set-Location $PSScriptRoot
$envFile = "env.product.replica.$n"
Get-Content $envFile | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.*)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}
Set-Location db_layer\product
python product_server.py

# Usage:
# .\run_product_replica.ps1 <replica_number>
