import sys
import zipfile
from pathlib import Path, PurePosixPath
from lxml import etree
from urllib.parse import unquote
import last_folder_helper
from complex_scan import find_opf_path
from check_copyright import parse_opf, resolve_href, get_spine_xhtml_paths, extract_text_from_xhtml, score_file, CONFIDENCE_THRESHOLD

def normalize_path(base_path, href, namelist):
    decoded = unquote(href)
    if decoded in namelist:
        return decoded
    if not base_path:
        return PurePosixPath(decoded).as_posix()
    resolved = (PurePosixPath(base_path).parent / PurePosixPath(decoded)).as_posix()
    parts = PurePosixPath(resolved).parts
    normalized = []
    for part in parts:
        if part == '..':
            if normalized:
                normalized.pop()
        elif part != '.':
            normalized.append(part)
    return '/'.join(normalized) if normalized else ''

def strip_fragment(href):
    return href.split('#', 1)[0]

def find_copyright_path(z, manifest, spine, opf_dir):
    xhtml_paths = get_spine_xhtml_paths(z, manifest, spine, opf_dir)
    if not xhtml_paths:
        return None
    best_index = None
    best_score = 0
    second_score = 0
    for i, zip_path in enumerate(xhtml_paths):
        text = extract_text_from_xhtml(z, zip_path)
        score = score_file(zip_path, text)
        if score > best_score:
            second_score = best_score
            best_score = score
            best_index = i
        elif score > second_score:
            second_score = score
    if best_score < CONFIDENCE_THRESHOLD:
        return None
    if best_score > 0 and second_score > 0 and best_score < second_score * 1.5:
        return None
    return xhtml_paths[best_index]

def extract_nav_toc_hrefs(z, opf_dir, manifest):
    for item in manifest.values():
        props = (item.get('properties') or '')
        if 'nav' not in props.split():
            continue
        nav_path = resolve_href(opf_dir, item['href'])
        if nav_path not in z.namelist():
            continue
        try:
            with z.open(nav_path) as f:
                parser = etree.HTMLParser(recover=True)
                tree = etree.parse(f, parser)
                root = tree.getroot()
                navs = root.findall('.//{http://www.w3.org/1999/xhtml}nav') or root.findall('.//nav')
                for nav in navs:
                    epub_type = nav.get('{http://www.idpf.org/2007/ops}type') or nav.get('epub:type') or ''
                    if 'toc' in epub_type or 'toc' in (nav.get('id') or '').lower():
                        anchors = nav.findall('.//{http://www.w3.org/1999/xhtml}a') or nav.findall('.//a')
                        return [(a.get('href'), nav_path) for a in anchors if a.get('href')]
                anchors = root.findall('.//{http://www.w3.org/1999/xhtml}a') or root.findall('.//a')
                return [(a.get('href'), nav_path) for a in anchors if a.get('href')]
        except Exception:
            continue
    return []

def extract_ncx_hrefs(z, opf_dir, manifest, spine_toc):
    ncx_id = None
    if spine_toc and spine_toc in manifest:
        ncx_id = spine_toc
    else:
        for iid, item in manifest.items():
            if (item.get('media-type') or '') == 'application/x-dtbncx+xml':
                ncx_id = iid
                break
    if not ncx_id:
        return []
    ncx_href = resolve_href(opf_dir, manifest[ncx_id]['href'])
    if ncx_href not in z.namelist():
        return []
    try:
        with z.open(ncx_href) as f:
            parser = etree.XMLParser(recover=True)
            tree = etree.parse(f, parser)
            root = tree.getroot()
            ncx_ns = (root.nsmap or {}).get(None, '')
            if ncx_ns:
                content_elems = tree.findall(f'{{{ncx_ns}}}navMap//{{{ncx_ns}}}content')
                if not content_elems:
                    content_elems = tree.findall(f'.//{{{ncx_ns}}}content')
            else:
                content_elems = tree.findall('.//content')
            return [(c.get('src'), ncx_href) for c in content_elems if c.get('src')]
    except Exception:
        return []

def extract_human_toc_hrefs(z, manifest, spine, opf_dir):
    results = []
    for idref in spine:
        item = manifest.get(idref)
        if not item:
            continue
        href = resolve_href(opf_dir, item['href'])
        filename = PurePosixPath(href).name.lower()
        if 'toc' not in filename and 'contents' not in filename:
            continue
        if href not in z.namelist():
            continue
        try:
            with z.open(href) as f:
                parser = etree.HTMLParser(recover=True)
                tree = etree.parse(f, parser)
                anchors = tree.findall('.//{http://www.w3.org/1999/xhtml}a') or tree.findall('.//a')
                for a in anchors:
                    link = a.get('href')
                    if link:
                        results.append((link, href))
        except Exception:
            continue
    return results

def hrefs_contain_path(hrefs, copyright_path, namelist):
    found_in = []
    target_parts = PurePosixPath(copyright_path).parts
    for href, source_path in hrefs:
        base = strip_fragment(href)
        normalized = normalize_path(source_path, base, namelist)
        if PurePosixPath(normalized).parts == target_parts:
            found_in.append(source_path)
    return found_in

def parse_opf_with_toc(z, opf_path):
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
        spine_toc = None
        spine_el = root.find('opf:spine', ns)
        if spine_el is not None:
            spine_toc = spine_el.get('toc')
            for itemref in spine_el.findall('opf:itemref', ns):
                idref = itemref.get('idref')
                if idref:
                    spine.append(idref)
        opf_dir = PurePosixPath(opf_path).parent.as_posix()
        return manifest, spine, opf_dir, spine_toc

def analyze_epub(epub_path):
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            opf_path = find_opf_path(z)
            if opf_path is None:
                return None
            manifest, spine, opf_dir, spine_toc = parse_opf_with_toc(z, opf_path)
            copyright_path = find_copyright_path(z, manifest, spine, opf_dir)
            if copyright_path is None:
                return None
            nav_hrefs = extract_nav_toc_hrefs(z, opf_dir, manifest)
            ncx_hrefs = extract_ncx_hrefs(z, opf_dir, manifest, spine_toc)
            human_hrefs = extract_human_toc_hrefs(z, manifest, spine, opf_dir)
            namelist = set(z.namelist())
            hits = []
            if hrefs_contain_path(nav_hrefs, copyright_path, namelist):
                hits.append('nav')
            if hrefs_contain_path(ncx_hrefs, copyright_path, namelist):
                hits.append('ncx')
            if hrefs_contain_path(human_hrefs, copyright_path, namelist):
                hits.append('human toc page')
            return hits if hits else None
    except Exception:
        return None

def main(folder):
    p = Path(folder).expanduser().resolve()
    if not p.is_dir():
        print(f"Folder not found: {p}")
        sys.exit(1)
    epub_paths = sorted(p.rglob('*.epub'))
    if not epub_paths:
        print("No EPUB files found")
        return
    found = 0
    for epub_path in epub_paths:
        hits = analyze_epub(str(epub_path))
        if hits:
            found += 1
            name = epub_path.name.replace('.epub', '')
            print(f"{name}: {', '.join(hits)}")
    if found == 0:
        print("No copyright pages found in any TOC")

if __name__ == "__main__":
    default = last_folder_helper.get_last_folder()
    user_input = input(f'Input folder ({default}): ').strip()
    folder = user_input or default
    if not folder:
        folder = '.'
    last_folder_helper.save_last_folder(folder)
    main(folder)

