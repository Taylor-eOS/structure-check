from zipfile import ZipFile
from pathlib import Path, PurePosixPath
from lxml import etree
import last_folder_helper
from complex_scan import find_opf_path

def parse_opf(z, opf_path):
    with z.open(opf_path) as f:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(f, parser)
        root = tree.getroot()
        opf_ns = 'http://www.idpf.org/2007/opf'
        if root.nsmap:
            for prefix, ns in root.nsmap.items():
                if ns and ns.endswith('/opf'):
                    opf_ns = ns
                    break
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
    clean_href = PurePosixPath(href)
    if '..' in clean_href.parts:
        return None
    if not opf_dir:
        return clean_href.as_posix()
    return (PurePosixPath(opf_dir) / clean_href).as_posix()

def get_css_files_from_manifest(manifest):
    css_files = set()
    for item_id, item_data in manifest.items():
        media_type = item_data.get('media-type', '')
        href = item_data.get('href', '')
        if media_type == 'text/css' or href.lower().endswith('.css'):
            css_filename = PurePosixPath(href).name
            css_files.add(css_filename)
    return css_files

def check_css_links_in_html(html_bytes, css_filenames):
    try:
        parser = etree.HTMLParser(recover=True)
        tree = etree.fromstring(html_bytes, parser)
    except Exception as e:
        return set()
    head = tree.find('.//{http://www.w3.org/1999/xhtml}head') or tree.find('.//head')
    if head is None:
        return set()
    linked_css = set()
    for link in head.findall('.//{http://www.w3.org/1999/xhtml}link') or head.findall('.//link'):
        rel = link.get('rel', '')
        href = link.get('href', '')
        if 'stylesheet' in rel.lower() and href:
            linked_filename = PurePosixPath(href).name
            linked_css.add(linked_filename)
    return linked_css

def analyze_epub_css_links(epub_path):
    try:
        with ZipFile(epub_path, 'r') as z:
            opf_path = find_opf_path(z)
            if not opf_path:
                return None
            try:
                manifest, spine, opf_dir = parse_opf(z, opf_path)
            except Exception as e:
                return None
            css_files = get_css_files_from_manifest(manifest)
            if not css_files:
                return []
            spine_files = []
            for idref in spine:
                item = manifest.get(idref)
                if not item:
                    continue
                href = resolve_href(opf_dir, item['href'])
                if href is None:
                    continue
                media_type = item.get('media-type', '')
                if media_type in ('application/xhtml+xml', 'text/html') or href.lower().endswith(('.xhtml', '.html', '.htm')):
                    spine_files.append(href)
            files_missing_css = []
            for sf in spine_files:
                sf_lower = sf.lower()
                is_exempt = any(term in sf_lower for term in ['titlepage', 'titlingpage', 'wrap', 'cover'])
                try:
                    with z.open(sf) as fh:
                        data = fh.read()
                except KeyError:
                    continue
                except Exception as e:
                    continue
                linked_in_file = check_css_links_in_html(data, css_files)
                if not linked_in_file and not is_exempt:
                    files_missing_css.append(sf)
            return files_missing_css
    except Exception as e:
        return None

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
        try:
            files_missing_css = analyze_epub_css_links(str(epub))
        except Exception as e:
            print(f"Error analyzing {epub.name}: {e}")
            continue
        if files_missing_css is None:
            continue
        if files_missing_css:
            print(f"{epub.name}:")
            for missing_file in files_missing_css:
                print(f"  - {missing_file}")

if __name__ == "__main__":
    default = last_folder_helper.get_last_folder()
    user_input = input(f'Input folder ({default}): ').strip()
    folder = user_input or default
    if not folder:
        folder = '.'
    last_folder_helper.save_last_folder(folder)
    main(folder)

