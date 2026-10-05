param(
    [Parameter(Mandatory=$true)][string]$ProjectDir,
    [int]$Width = 1920,
    [switch]$Pdf
)
$ErrorActionPreference = 'Stop'
if ($Width -le 0 -or $Width % 16 -ne 0) { throw 'Preview width must be a positive multiple of 16.' }
$project = (Resolve-Path -LiteralPath $ProjectDir).Path
$pptx = Join-Path $project '07_delivery/deck.pptx'
$spec = Get-Content -LiteralPath (Join-Path $project '06_build/deck-spec.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$deckHash = (Get-FileHash -LiteralPath $pptx -Algorithm SHA256).Hash.ToLowerInvariant()
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff')
$relative = "07_delivery/preview/render-$stamp"
$output = Join-Path $project $relative
New-Item -ItemType Directory -Path $output -Force | Out-Null
$app = $null
$deck = $null
try {
    $app = New-Object -ComObject PowerPoint.Application
    $deck = $app.Presentations.Open($pptx, -1, 0, 0)
    if ($deck.Slides.Count -ne $spec.slides.Count) { throw 'Rendered slide count differs from specification.' }
    if ([Math]::Abs($deck.PageSetup.SlideWidth / $deck.PageSetup.SlideHeight - 16.0 / 9.0) -gt 0.000001) { throw 'Preview canvas must be exactly 16:9.' }
    $height = [int]($Width / 16 * 9)
    $pages = @()
    for ($index = 1; $index -le $deck.Slides.Count; $index++) {
        $id = $spec.slides[$index - 1].id
        if ($id -notmatch '^S[0-9]{2,}$') { throw 'Unsafe slide identifier.' }
        $image = Join-Path $output "$id.png"
        $deck.Slides.Item($index).Export($image, 'PNG', $Width, $height)
        $pages += @{ id=$id; path="$relative/$id.png"; sha256=(Get-FileHash -LiteralPath $image).Hash.ToLowerInvariant() }
    }
    if ((Get-FileHash -LiteralPath $pptx).Hash.ToLowerInvariant() -ne $deckHash) { throw 'PPTX changed during rendering.' }
    $pdfPath = $null
    $pdfHash = $null
    if ($Pdf) {
        $pdfTarget = Join-Path $project '07_delivery/deck.pdf'
        $pdfTemporary = Join-Path $project '07_delivery/deck.tmp.pdf'
        if (Test-Path -LiteralPath $pdfTemporary) { Remove-Item -LiteralPath $pdfTemporary -Force }
        $deck.SaveAs($pdfTemporary, 32)
        if (-not (Test-Path -LiteralPath $pdfTemporary)) { throw 'PDF export failed.' }
        Move-Item -LiteralPath $pdfTemporary -Destination $pdfTarget -Force
        $pdfPath = '07_delivery/deck.pdf'
        $pdfHash = (Get-FileHash -LiteralPath $pdfTarget -Algorithm SHA256).Hash.ToLowerInvariant()
        if ((Get-FileHash -LiteralPath $pptx).Hash.ToLowerInvariant() -ne $deckHash) { throw 'PPTX changed during PDF export.' }
    }
    $manifest = @{
        renderer='Microsoft PowerPoint'; version=$app.Version; rendered_at=[DateTime]::UtcNow.ToString('o')
        pptx_sha256=$deckHash; width=$Width; height=$height; pages=$pages
        pdf_path=$pdfPath; pdf_sha256=$pdfHash
    }
    $json = $manifest | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText((Join-Path $project '07_delivery/render-manifest.json'), $json, [System.Text.UTF8Encoding]::new($false))
    Write-Output $json
} finally {
    if ($null -ne $deck) { $deck.Close(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($deck) }
    if ($null -ne $app) { $app.Quit(); [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) }
}
