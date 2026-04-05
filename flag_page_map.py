from zipfile import ZipFile, BadZipFile
from pathlib import Path
from lxml import etree
import last_folder_helper
from complex_scan import find_opf_path

def check_page_map(epub_path):
    try:
        with ZipFile(epub_path, 'r') as z:
            opf_path = find_opf_path(z)
            if not opf_path:
                return 'no_opf', []
            with z.open(opf_path) as f:
                root = etree.parse(f, etree.XMLParser(recover=True)).getroot()
            nsmap = root.nsmap or {}
            opf_ns = 'http://www.idpf.org/2007/opf'
            for ns in nsmap.values():
                if ns and 'opf' in ns:
                    opf_ns = ns
                    break
            ns = {'opf': opf_ns}
            hits = []
            spine_el = root.find('opf:spine', ns)
            if spine_el is not None:
                for attr_name, attr_val in spine_el.attrib.items():
                    local = attr_name.split('}')[-1] if '}' in attr_name else attr_name
                    if 'page-map' in local.lower() or 'page-map' in attr_val.lower():
                        hits.append(f'spine attr: {local}="{attr_val}"')
            manifest_el = root.find('opf:manifest', ns)
            if manifest_el is not None:
                for item in manifest_el.findall('opf:item', ns):
                    iid = item.get('id', '')
                    mt = item.get('media-type', '')
                    href = item.get('href', '')
                    if ('page-map' in iid.lower()
                            or 'page-map' in mt.lower()
                            or href.lower().endswith('.ncx') is False and 'page-map' in href.lower()):
                        hits.append(f'manifest item: id="{iid}" media-type="{mt}" href="{href}"')
            return 'ok', hits
    except BadZipFile:
        return 'bad_zip', []
    except Exception as e:
        return f'error: {e}', []

def main(folder):
    p = Path(folder).expanduser().resolve()
    if not p.is_dir():
        print(f"Folder not found: {p}")
        return
    epub_paths = sorted(p.rglob('*.epub'))
    if not epub_paths:
        print("No EPUB files found")
        return
    flagged = 0
    for epub in epub_paths:
        status, hits = check_page_map(str(epub))
        if status != 'ok':
            print(f"{epub.name}: {status}")
            continue
        if hits:
            flagged += 1
            print(f"{epub.name}:")
            for hit in hits:
                print(f"  {hit}")
    if flagged == 0:
        print("No page-map usage found.")

if __name__ == '__main__':
    default = last_folder_helper.get_last_folder()
    user_input = input(f'Input folder ({default}): ').strip()
    folder = user_input or default
    if not folder:
        folder = '.'
    last_folder_helper.save_last_folder(folder)
    main(folder)

