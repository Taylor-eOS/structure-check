import zipfile
from pathlib import Path
import last_folder_helper

print_if_none = False
min_size = 1024

def main(folder):
    p = Path(folder).expanduser().resolve()
    if not p.is_dir():
        print(f"Folder not found: {p}")
        return
    epub_paths = sorted(p.rglob('*.epub'))
    if not epub_paths:
        print("No EPUB files")
        return
    for epub_path in epub_paths:
        try:
            with zipfile.ZipFile(epub_path) as z:
                png_files = []
                for info in z.infolist():
                    if info.filename.lower().endswith('.png'):
                        png_files.append(info.filename)
                has_png = len(png_files) > 0
                if has_png:
                    total_size = sum(z.getinfo(f).file_size for f in png_files)
                    size_kb = total_size / 1024
                    if size_kb > min_size:
                        print(f"{epub_path.stem[:30]:30} contains {len(png_files) if len(png_files) else 'N/A'} PNGs, {size_kb:.1f}KB total" if size_kb else "")
                else:
                    if print_if_none: print(f"{epub_path.stem} contains no PNGs")
        except Exception as e:
            print(f"{epub_path.stem}: failed to process ({e})")

if __name__ == "__main__":
    default = last_folder_helper.get_last_folder()
    user_input = input(f'Input folder ({default}): ').strip()
    folder = user_input or default
    if not folder:
        folder = '.'
    last_folder_helper.save_last_folder(folder)
    main(folder)

