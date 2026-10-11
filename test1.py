"""文件整理引擎：只扫描第一层；预览无副作用；执行固定计划。"""
from dataclasses import dataclass, replace
from pathlib import Path
import os
import shutil
import sys


CATEGORIES = {
    "images": "jpg jpeg png gif bmp webp svg ico tif tiff heic heif avif raw",
    "documents": "pdf doc docx odt rtf txt md epub mobi pages",
    "spreadsheets": "xls xlsx xlsm csv tsv ods numbers",
    "presentations": "ppt pptx odp key",
    "audio": "mp3 wav flac aac ogg m4a wma opus aiff",
    "video": "mp4 mkv avi mov wmv flv webm m4v mpeg mpg ts",
    "archives": "zip rar 7z tar gz bz2 xz tgz tar.gz tar.bz2 tar.xz",
    "code": "py pyw java js ts jsx tsx html css scss c cpp h hpp cs go rs php rb swift kt sh bat ps1 sql ipynb",
    "data": "json xml yaml yml toml ini db sqlite sqlite3 parquet",
    "installers": "exe msi msix apk dmg pkg deb rpm",
    "fonts": "ttf otf woff woff2",
    "design": "psd ai eps sketch fig blend obj stl fbx dwg dxf",
}
EXTENSIONS = {'.' + ext: category for category, extensions in CATEGORIES.items()
              for ext in extensions.split()}
SORTED_EXTENSIONS = sorted(EXTENSIONS, key=len, reverse=True)


@dataclass(frozen=True)
class Entry:
    source: Path
    destination: Path | None
    kind: str
    status: str
    detail: str = ""
    signature: tuple | None = None


@dataclass(frozen=True)
class Plan:
    folder: Path
    entries: tuple[Entry, ...]


def fingerprint(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def file_kind(path):
    name = path.name.lower()
    return next((ext for ext in SORTED_EXTENSIONS if name.endswith(ext)), path.suffix.lower())


def protected_files():
    here = Path(__file__).resolve().parent
    protected = {here / 'test1.py', here / 'gui_v2.py', Path(__file__).resolve()}
    if getattr(sys, 'frozen', False):
        protected.add(Path(sys.executable).resolve())
    return protected


def path_key(path):
    # Windows 文件名大小写不敏感；在其他系统也采取保守策略。
    return str(path).casefold()


def build_plan(folder, conflict='skip', include_unknown=False):
    if conflict not in ('skip', 'rename'):
        raise ValueError('同名处理必须为 skip 或 rename')
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError('请选择文件夹')
    entries, reserved = [], set()
    protected = protected_files()
    for source in sorted(root.iterdir(), key=lambda p: (p.name.casefold(), p.name)):
        kind = file_kind(source)
        if source.is_symlink() or source.is_junction():
            entries.append(Entry(source, None, kind, 'Skipped', '符号链接或目录联接不处理'))
            continue
        if source.is_dir():
            continue
        try:
            if not source.is_file():
                entries.append(Entry(source, None, kind, 'Skipped', '不是普通文件'))
                continue
            signature = fingerprint(source)
            if source.resolve() in protected:
                entries.append(Entry(source, None, kind, 'Skipped', '保护程序自身'))
                continue
            category = EXTENSIONS.get(kind, 'others' if include_unknown else None)
            if category is None:
                entries.append(Entry(source, None, kind, 'Skipped', '未识别类型'))
                continue
            target_dir = root / category
            if target_dir.is_symlink() or target_dir.is_junction() or (target_dir.exists() and not target_dir.is_dir()):
                entries.append(Entry(source, None, kind, 'Skipped', '分类目录被文件或链接占用'))
                continue
            destination = target_dir / source.name
            count = 0
            while os.path.lexists(destination) or path_key(destination) in reserved:
                if conflict == 'skip':
                    break
                count += 1
                stem = source.name[:-len(kind)] if kind else source.name
                suffix = source.name[-len(kind):] if kind else ''
                destination = target_dir / f'{stem} ({count}){suffix}'
            else:
                reserved.add(path_key(destination))
                entries.append(Entry(source, destination, kind, 'Ready',
                                     '同名自动重命名' if count else '', signature))
                continue
            entries.append(Entry(source, destination, kind, 'Skipped', '目标存在同名文件', signature))
        except OSError as error:
            entries.append(Entry(source, None, kind, 'Failed', str(error)))
    return Plan(root, tuple(entries))


def execute_plan(plan, progress=None):
    """只执行预览中 Ready 项；不覆盖目标；逐项隔离错误。"""
    results = []
    for index, entry in enumerate(plan.entries, 1):
        result = entry
        if entry.status == 'Ready':
            destination = entry.destination
            created = False
            try:
                if entry.source.parent != plan.folder or destination is None or destination.parent.parent != plan.folder:
                    raise ValueError('计划路径不合法')
                if entry.source.is_symlink() or fingerprint(entry.source) != entry.signature:
                    result = replace(entry, status='Skipped', detail='源文件已变化，请重新预览')
                else:
                    parent = destination.parent
                    if parent.is_symlink() or parent.is_junction():
                        raise OSError('分类目录已变成链接，请重新预览')
                    parent.mkdir(exist_ok=True)
                    # xb 原子拒绝已有目标，避免预览后新增的同名文件被覆盖。
                    with entry.source.open('rb') as reader, destination.open('xb') as writer:
                        created = True
                        shutil.copyfileobj(reader, writer)
                        writer.flush()
                        os.fsync(writer.fileno())
                    shutil.copystat(entry.source, destination)
                    if fingerprint(entry.source) != entry.signature:
                        raise OSError('复制过程中源文件发生变化，保留源文件')
                    entry.source.unlink()
                    result = replace(entry, status='Success', detail='已整理')
            except FileExistsError:
                result = replace(entry, status='Skipped', detail='目标已存在，请重新预览')
            except (OSError, ValueError) as error:
                detail = str(error)
                if created:
                    try:
                        destination.unlink()
                    except OSError as cleanup_error:
                        detail += f'；目标副本清理失败：{cleanup_error}'
                result = replace(entry, status='Failed', detail=detail)
        results.append(result)
        if progress:
            progress(index, len(plan.entries))
    return Plan(plan.folder, tuple(results))


def summarize(plan):
    return {key: sum(entry.status == status for entry in plan.entries)
            for key, status in [('preview', 'Ready'), ('success', 'Success'),
                                ('skip', 'Skipped'), ('fail', 'Failed')]}


def organize_files(folder, preview=True, *, conflict='skip', include_unknown=False):
    """保留旧调用接口；需要严格对应预览时使用 build_plan / execute_plan。"""
    plan = build_plan(folder, conflict, include_unknown)
    if not preview:
        plan = execute_plan(plan)
    return {**summarize(plan), 'files': [
        {'name': e.source.name, 'type': e.kind,
         'destination': str(e.destination.relative_to(plan.folder)) if e.destination else '',
         'status': e.status, 'detail': e.detail} for e in plan.entries]}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='预览文件整理（不会移动文件）')
    parser.add_argument('folder', nargs='?', default='.')
    args = parser.parse_args()
    print(organize_files(args.folder))
