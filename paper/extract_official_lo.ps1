$ErrorActionPreference = 'Stop'
$paperRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$msiPath = Join-Path $paperRoot 'runtime/LibreOffice_26.2.6_Win_x86-64.msi'
$sourceRoot = Join-Path $paperRoot 'runtime/lo-extracted'
$destRoot = Join-Path $paperRoot 'runtime/libreoffice'
$installer = New-Object -ComObject WindowsInstaller.Installer
$database = $installer.OpenDatabase($msiPath,0)
function Read-MsiTable($sql,$columns) {
    $view=$database.OpenView($sql); $view.Execute() | Out-Null
    $result=[Collections.Generic.List[object]]::new()
    while($record=$view.Fetch()) {
        $row=@{}
        for($i=0;$i -lt $columns.Count;$i++) { $row[$columns[$i]]=$record.StringData($i+1) }
        $result.Add($row)
    }
    $view.Close() | Out-Null
    return $result
}
$directories=@{}
foreach($row in (Read-MsiTable 'SELECT Directory, Directory_Parent, DefaultDir FROM Directory' @('id','parent','name'))) { $directories[$row.id]=$row }
$components=@{}
foreach($row in (Read-MsiTable 'SELECT Component, Directory_ FROM Component' @('id','dir'))) { $components[$row.id]=$row.dir }
function Resolve-MsiDirectory($id) {
    if(!$id -or $id -eq 'TARGETDIR' -or $id -eq 'ProgramFiles64Folder' -or $id -eq 'ProgramFilesFolder') { return '' }
    $row=$directories[$id]
    if(!$row) { throw "Missing directory $id" }
    $parent=Resolve-MsiDirectory $row.parent
    $name=($row.name -split ':')[0]
    if($name.Contains('|')) { $name=($name -split '\|')[-1] }
    if($name -eq '.') { return $parent }
    if($parent) { return (Join-Path $parent $name) }
    return $name
}
$count=0
foreach($row in (Read-MsiTable 'SELECT File, Component_, FileName FROM File' @('id','component','name'))) {
    $relative=Resolve-MsiDirectory $components[$row.component]
    $name=($row.name -split '\|')[-1]
    $target=[IO.Path]::GetFullPath((Join-Path (Join-Path $destRoot $relative) $name))
    if(!$target.StartsWith($destRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'MSI path outside runtime' }
    $source=Join-Path $sourceRoot $row.id
    if(!(Test-Path -LiteralPath $source)) { throw "Missing CAB file $($row.id)" }
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
    [IO.File]::Copy($source,$target,$true)
    $count++
}
Write-Output "Reconstructed $count files under $destRoot"
Get-ChildItem -LiteralPath $destRoot -Filter soffice.exe -Recurse | Select-Object FullName,Length
