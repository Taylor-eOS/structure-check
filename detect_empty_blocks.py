import sys
from zipfile import ZipFile
from pathlib import Path, PurePosixPath
from lxml import etree
import last_folder_helper

TABLE_TAGS = {'table', 'tbody', 'thead', 'tfoot', 'tr', 'td', 'th'}
MIN_BLOCKS = 20
EMPTY_RATIO_THRESHOLD = 0.25

def find_opf_path(z):
    try:
        with z.open('META-INF/container.xml') as f:
            tree = etree.parse(f)
            rootfile = tree.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
            if rootfile is not None:
                return rootfile.get('full-path')
    except Exception:
        pass
    for name in z.namelist():
        if name.lower().endswith('.opf'):
            return name
    return None

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
                props = item.get('properties') or ''
                if iid and href:
                    manifest[iid] = {'href': href, 'media-type': media, 'properties': props}
        spine = []
        spine_el = root.find('opf:spine', ns)
        if spine_el is not None:
            for itemref in spine_el.findall('opf:itemref', ns):
                idref = itemref.get('idref')
                if idref:
                    spine.append(idref)
        opf_dir = PurePosixPath(opf_path).parent.as_posix()
        return manifest, spine, opf_dir

def resolve_href(opf_dir, href):
    if not opf_dir:
        return PurePosixPath(href).as_posix()
    return (PurePosixPath(opf_dir) / PurePosixPath(href)).as_posix()

def analyze_blocks_in_html_bytes(html_bytes):
    parser = etree.HTMLParser(recover=True)
    tree = etree.fromstring(html_bytes, parser)
    body = tree.find('.//{http://www.w3.org/1999/xhtml}body') or tree.find('.//body')
    if body is None:
        return 0, 0
    total = 0
    empty = 0
    for child in body:
        if not isinstance(child.tag, str):
            continue
        tag = etree.QName(child.tag).localname.lower()
        if tag in TABLE_TAGS:
            continue
        text = ''.join(child.itertext())
        if text is None:
            text = ''
        text = text.replace('\xa0', ' ').strip()
        total += 1
        if text == '':
            empty += 1
    return total, empty

def analyze_epub_empty_blocks(epub_path, min_blocks=MIN_BLOCKS, threshold=EMPTY_RATIO_THRESHOLD):
    findings = []
    try:
        with ZipFile(epub_path, 'r') as z:
            opf_path = find_opf_path(z)
            if not opf_path:
                return findings
            manifest, spine, opf_dir = parse_opf(z, opf_path)
            spine_files = []
            for idref in spine:
                item = manifest.get(idref)
                if not item:
                    continue
                href = resolve_href(opf_dir, item['href'])
                if href.lower().endswith(('.xhtml', '.html', '.htm')):
                    spine_files.append(href)
            for sf in spine_files:
                try:
                    with z.open(sf) as fh:
                        data = fh.read()
                except KeyError:
                    continue
                total, empty = analyze_blocks_in_html_bytes(data)
                if total >= min_blocks:
                    ratio = empty / total if total else 0
                    if ratio >= threshold:
                        findings.append((sf, total, empty, ratio))
    except Exception:
        return findings
    return findings

def main(folder):
    p = Path(folder).expanduser().resolve()
    if not p.is_dir():
        print(f"Folder not found: {p}")
        return
    epub_paths = sorted(p.rglob('*.epub'))
    if not epub_paths:
        print("No EPUB files found")
        return
    for epub in epub_paths:
        results = analyze_epub_empty_blocks(str(epub))
        if not results:
            continue
        worst = max(results, key=lambda x: x[3])
        sf, total, empty, ratio = worst
        print(f"{epub.name.strip('.epub')}: {len(results)} spine files exceed threshold, worst {sf} empty={empty}/{total} ratio={ratio:.2f}")

if __name__ == "__main__":
    default = last_folder_helper.get_last_folder()
    user_input = input(f'Input folder ({default}): ').strip()
    folder = user_input or default
    if not folder:
        folder = '.'
    last_folder_helper.save_last_folder(folder)
    main(folder)

