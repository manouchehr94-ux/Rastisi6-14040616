Set-Location $PSScriptRoot
Write-Host "Homepage: http://localhost:8000/"
Write-Host "Product:  http://localhost:8000/product/"
python -m http.server 8000
