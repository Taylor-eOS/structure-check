import sys
import zipfile
from pathlib import Path, PurePosixPath
from lxml import etree
import last_folder_helper
from complex_scan import find_opf_path

def resolve_href(opf_dir, href):
    return (PurePosixPath(opf_dir) / PurePosixPath(href)).as_posix()

def parse_opf(z, opf_path):
    with z.open(opf_path) as f:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(f, parser)
        root = tree.getroot()
        opf_ns = None
        for ns in (root.nsmap or {}).values():
            if ns and 'opf' in ns:
                opf_ns = ns
                break
        if opf_ns is None:
            opf_ns = 'http://www.idpf.org/2007/opf'
        ns = {'opf': opf_ns}
        manifest = {}
        manifest_el = root.find('opf:manifest', ns)
        if manifest_el is not None:
            for item in manifest_el.findall('opf:item', ns):
                iid = item.get('id')
                href = item.get('href')
                media = item.get('media-type')
                if iid and href:
                    manifest[iid] = {'href': href, 'media-type': media}
        opf_dir = PurePosixPath(opf_path).parent.as_posix()
        return manifest, opf_dir, root, ns

def find_first_two_content_paths(z, manifest, opf_dir, root, ns):
    spine = root.find('opf:spine', ns)
    if spine is None:
        return []
    results = []
    for itemref_el in spine.findall('opf:itemref', ns):
        if itemref_el.get('linear', 'yes') != 'no':
            idref = itemref_el.get('idref')
            if idref and idref in manifest:
                item = manifest[idref]
                mt = item['media-type']
                if mt in ('application/xhtml+xml', 'text/html'):
                    results.append(resolve_href(opf_dir, item['href']))
                    if len(results) == 2:
                        break
    return results

def page_has_image(z, zip_path):
    xhtml_ns = 'http://www.w3.org/1999/xhtml'
    svg_ns = 'http://www.w3.org/2000/svg'
    try:
        with z.open(zip_path) as f:
            tree = etree.parse(f, etree.XMLParser(recover=True))
        for tag in (f'.//{{{xhtml_ns}}}img', f'.//{{{svg_ns}}}image', f'.//{{{xhtml_ns}}}image'):
            if tree.findall(tag):
                return True
        if tree.findall(f'.//{{{xhtml_ns}}}svg') or tree.findall(f'.//{{{svg_ns}}}svg'):
            return True
    except Exception:
        pass
    return False

def process_epub(epub_path):
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            opf_path = find_opf_path(z)
            if opf_path is None:
                return None
            manifest, opf_dir, root, ns = parse_opf(z, opf_path)
            paths = find_first_two_content_paths(z, manifest, opf_dir, root, ns)
            if len(paths) < 2:
                return None
            first_has = page_has_image(z, paths[0])
            second_has = page_has_image(z, paths[1])
            return first_has, second_has
    except Exception:
        return None

def main(epub_folder):
    p = Path(epub_folder).expanduser().resolve()
    if not p.is_dir():
        print(f"Folder not found: {p}")
        return
    epub_paths = sorted(p.rglob('*.epub'))
    if not epub_paths:
        print("No EPUB files found")
        return
    duplicates = []
    total = 0
    skipped = 0
    for epub_path in epub_paths:
        total += 1
        result = process_epub(epub_path)
        if result is None:
            skipped += 1
            continue
        first_has, second_has = result
        if first_has and second_has:
            duplicates.append(epub_path.name)
    print(f"Total EPUBs scanned:  {total}")
    print(f"Skipped:              {skipped}")
    print(f"Duplicate titlepages: {len(duplicates)}")
    if duplicates:
        print()
        for name in duplicates:
            print(f"  {name}")

if __name__ == "__main__":
    try:
        default = last_folder_helper.get_last_folder()
        user_input = input(f'Input folder ({default}): ').strip()
        folder = user_input or default
        if not folder:
            folder = '.'
        last_folder_helper.save_last_folder(folder)
    except ImportError:
        if len(sys.argv) > 1:
            folder = sys.argv[1]
        else:
            folder = input('Input folder: ').strip() or '.'
    print()
    main(folder)

