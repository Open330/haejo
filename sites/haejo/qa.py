#!/usr/bin/env python3
"""Browser checks for the served Haejo pages. Playwright is a QA-only dependency."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

DMG = 'https://github.com/Open330/haejo/releases/download/v1.0.1/Haejo-1.0.1-arm64.dmg'
SECTIONS = ['direct', 'history', 'flow', 'install', 'faq']
PAGES = {'ko': '', 'en': 'en/', 'ko_bench': 'benchmarks/', 'en_bench': 'en/benchmarks/'}
WIDTHS = [320, 360, 390, 768, 1024, 1440, 1600]


def audit(url, output, axe_source=None, browser_executable=None):
    output.mkdir(parents=True, exist_ok=True)
    output.chmod(0o700)
    base = url.rstrip('/') + '/'
    checks, errors, requests, accessibility = {}, [], [], {}
    origin = urlsplit(base)

    def run_axe(page, name):
        if axe_source:
            page.evaluate(axe_source)
            result = page.evaluate('axe.run()')
            accessibility[name] = result
            checks['axe_' + name] = not result['violations']

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(executable_path=browser_executable)
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        context.add_init_script('''
          Object.defineProperty(navigator,'clipboard',{value:undefined});
          const nativeCopy=document.execCommand.bind(document);
          document.execCommand=(name,...args)=>{
            if(name==='copy')window.__copied=document.querySelector('textarea.clipboard-fallback')?.value;
            return nativeCopy(name,...args);
          };
        ''')
        for name, path in PAGES.items():
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: requests.append(request.url))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            response = page.goto(base + path, wait_until='networkidle')
            home = not name.endswith('bench')
            lang = name[:2]
            checks[name + '_http_200'] = response.status == 200
            checks[name + '_lang'] = page.locator('html').get_attribute('lang') == lang
            checks[name + '_one_h1'] = page.locator('h1').count() == 1
            checks[name + '_csp'] = "default-src 'none'" in (page.locator('meta[http-equiv="Content-Security-Policy"]').get_attribute('content') or '')
            checks[name + '_no_inline_handlers_or_styles'] = page.evaluate(
                '''() => ![...document.querySelectorAll('*')].some(e => e.hasAttribute('style') ||
                    [...e.attributes].some(a => a.name.startsWith('on'))) && !document.querySelector('style, script:not([src])')''')
            checks[name + '_hreflang'] = page.locator('link[rel="alternate"]').evaluate_all(
                '(items)=>["ko","en","x-default"].every(l=>items.some(e=>e.hreflang===l&&e.href.startsWith("https://open330.github.io/haejo/")))')
            switch = page.request.get(page.locator('.nav-side a[hreflang]').evaluate('(a)=>a.href'))
            checks[name + '_language_switch'] = switch.status == 200 and ('lang="en"' if lang == 'ko' else 'lang="ko"') in switch.text()
            checks[name + '_download_is_current_release'] = page.locator('a[href*="/releases/download/"]').evaluate_all(
                '(items, dmg)=>items.length>=2&&items.every(e=>e.href===dmg)', DMG)
            checks[name + '_images_loaded_with_alt_and_size'] = page.locator('img').evaluate_all(
                '''async (items) => { for (const e of items) { e.loading = 'eager'; try { await e.decode(); } catch (x) { return false; } }
                    return items.every(e => e.naturalWidth > 0 && e.hasAttribute('alt') && e.width && e.height); }''')
            checks[name + '_anchors_resolve'] = page.evaluate('''() => [...document.querySelectorAll('a[href^="#"]')]
              .every(a=>!a.hash||document.getElementById(decodeURIComponent(a.hash.slice(1))))''')
            local = page.locator('a[href]').evaluate_all(
                '(items)=>[...new Set(items.map(e=>e.href.split("#")[0]).filter(h=>h.startsWith(location.origin)))]')
            checks[name + '_local_links_resolve'] = all(page.request.get(link).status == 200 for link in local)
            checks[name + '_external_links_are_isolated'] = page.locator('a[target="_blank"]').evaluate_all(
                '(items)=>items.every(e=>e.rel.includes("noopener"))')
            checks[name + '_vector_icons_render'] = page.locator('svg.icon use').evaluate_all(
                '(items)=>items.every(e=>e.getBBox().width>0&&e.getBBox().height>0)')
            page.keyboard.press('Tab')
            checks[name + '_skip_link_first'] = page.locator('.skip').evaluate('(e)=>e===document.activeElement')
            page.keyboard.press('Enter')
            checks[name + '_skip_focuses_main'] = page.evaluate('document.activeElement.id==="main"')
            checks[name + '_focus_ring'] = page.locator('.nav-cta').evaluate(
                '(e)=>{e.focus();return e.matches(":focus-visible")&&parseFloat(getComputedStyle(e).outlineWidth)>=2}')

            if home:
                checks[name + '_section_order'] = page.locator('main > section[id]').evaluate_all('(items)=>items.map(e=>e.id)') == SECTIONS
                checks[name + '_header_links_to_sections'] = page.locator('.nav-links a').evaluate_all('(items)=>items.map(e=>e.hash.slice(1))') == SECTIONS
                checks[name + '_one_film'] = page.locator('video').evaluate_all(
                    '(items, lang)=>items.length===1&&items.every(e=>e.controls&&!e.autoplay&&e.preload==="none"&&e.poster.includes("haejo-film."+lang)&&e.getAttribute("aria-label"))', lang)
                video = page.locator('video')
                video.evaluate('(e)=>e.load()')
                page.wait_for_function('()=>document.querySelector("video").readyState>=2')
                checks[name + '_film_decodes'] = video.evaluate('(e)=>e.duration>30&&e.videoWidth===1920&&!e.error')
                checks[name + '_no_separate_browser_claim'] = page.evaluate('!/Chromium/i.test(document.body.innerText)')
                checks[name + '_measured_scope_once'] = page.evaluate('(document.body.innerText.match(/Safari 27\\.2/g)||[]).length===1')
                checks[name + '_seven_step_flow'] = page.locator('.flow-steps li').count() == 7
                flow = page.request.get(base + 'assets/expense-entry.flow.json')
                source = flow.json()
                checks[name + '_flow_matches_source'] = (flow.status == 200 and source['name'] == 'expense-entry' and len(source['steps']) == 7
                    and page.locator('.flow-steps code').evaluate_all('(items)=>items.slice(0,6).map(e=>e.textContent.slice(2,-2))') == list(source['params']))
                checks[name + '_replay_adds_up'] = page.locator('.replay li b').evaluate_all(
                    '(items)=>Math.abs(items.reduce((s,e)=>s+parseFloat(e.textContent.replace(/[^0-9.]/g,"")),0)-20.7)<0.01&&items.length===6')
                checks[name + '_three_install_steps'] = page.locator('.steps > li').count() == 3
                copy = page.locator('[data-copy="first-prompt"]')
                copy.click()
                checks[name + '_copy_prompt'] = (page.evaluate('window.__copied') == page.locator('#first-prompt').inner_text().strip()
                    and page.locator('.clipboard-fallback').count() == 0)
                first = page.locator('.faq-list details').first
                first.locator('summary').click()
                checks[name + '_faq_opens'] = first.get_attribute('open') is not None
                checks[name + '_faq_links_benchmarks'] = page.locator('.faq-list a[href="benchmarks/"]').count() == 1
                first.locator('summary').click()
            else:
                checks[name + '_three_measurements'] = page.locator('main table').count() == 3
                checks[name + '_tables_labelled'] = page.locator('table').evaluate_all(
                    '(items)=>items.every(t=>t.caption&&t.querySelectorAll("th[scope]").length>=4)')
                summary = page.request.get(base + 'assets/benchmark-summary.json').json()['summary']
                text = page.locator('main').inner_text()
                checks[name + '_numbers_match_summary'] = all(f"{summary[arm][key]:,}" in text for arm in ('haejo', 'sky')
                    for key in ('total_input_tokens', 'new_input_tokens', 'output_tokens'))
                checks[name + '_names_the_compared_product'] = 'Codex' in text and 'OAI' not in text
            run_axe(page, name + '_desktop')

            for width in WIDTHS:
                page.set_viewport_size({'width': width, 'height': 844})
                checks[f'{name}_no_overflow_{width}'] = page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.set_viewport_size({'width': 390, 'height': 844})
            button, nav = page.locator('.menu-button'), page.locator('#nav')
            checks[name + '_mobile_menu_collapsed'] = button.is_visible() and not nav.is_visible()
            checks[name + '_mobile_header_fits'] = page.locator('.header').bounding_box()['height'] <= 72
            button.click()
            checks[name + '_mobile_menu_opens'] = nav.is_visible() and button.get_attribute('aria-expanded') == 'true'
            run_axe(page, name + '_mobile_menu')
            page.keyboard.press('Escape')
            checks[name + '_mobile_menu_escape'] = not nav.is_visible() and button.evaluate('(e)=>e===document.activeElement')
            checks[name + '_mobile_touch_targets'] = page.locator('button:visible, .button:visible').evaluate_all(
                '(items)=>items.every(e=>e.getBoundingClientRect().height>=44)')
            checks[name + '_mobile_body_text_size'] = page.locator('main p:visible').evaluate_all(
                '(items)=>items.every(e=>e.closest(".scene")||parseFloat(getComputedStyle(e).fontSize)>=13)')
            page.screenshot(path=str(output / f'{name}-mobile.png'), full_page=True)
            page.set_viewport_size({'width': 1440, 'height': 900})
            checks[name + '_desktop_menu_inline'] = nav.is_visible() and not button.is_visible()
            page.screenshot(path=str(output / f'{name}-desktop.png'), full_page=True)
            page.emulate_media(reduced_motion='reduce')
            checks[name + '_reduced_motion'] = page.evaluate(
                'getComputedStyle(document.documentElement).scrollBehavior==="auto"&&[...document.querySelectorAll("*")].every(e=>["none",""].includes(getComputedStyle(e).animationName))')
            page.emulate_media(reduced_motion='no-preference')
            checks[name + '_no_browser_storage'] = page.evaluate('localStorage.length===0&&sessionStorage.length===0&&document.cookie===""')
            page.close()

        shapes = []
        for path in (PAGES['ko'], PAGES['en']):
            page = context.new_page()
            page.goto(base + path, wait_until='networkidle')
            shapes.append(page.evaluate('''() => [...document.querySelectorAll('main *:not(h1 small)')].map(e => e.tagName + '.' + e.className).join('|')
                + [...document.querySelectorAll('img, source')].map(e => (e.getAttribute('src') || e.getAttribute('srcset')).replace(/\\.(ko|en)\\./, '.').replace(/^\\.\\.\\//, '')).join('|')'''))
            page.close()
        checks['ko_en_same_structure'] = shapes[0] == shapes[1]
        checks['no_external_requests'] = all(urlsplit(item).netloc == origin.netloc for item in requests)
        checks['no_script_or_console_errors'] = not errors
        context.close()

        nojs = browser.new_context(java_script_enabled=False, viewport={'width': 390, 'height': 844})
        fallback = nojs.new_page()
        fallback.goto(base, wait_until='networkidle')
        checks['nojs_navigation_visible'] = fallback.locator('.nav-links a').first.is_visible() and not fallback.locator('.menu-button').is_visible()
        checks['nojs_download_present'] = fallback.locator(f'#install a[href="{DMG}"]').is_visible()
        checks['nojs_copy_hidden'] = not fallback.locator('[data-copy]').is_visible()
        checks['nojs_video_controls'] = fallback.locator('video').evaluate('(e)=>e.controls')
        fallback.locator('.faq-list summary').first.click()
        checks['nojs_faq_works'] = fallback.locator('.faq-list details').first.get_attribute('open') is not None
        checks['nojs_no_overflow'] = fallback.evaluate('document.documentElement.scrollWidth<=innerWidth')
        nojs.close()
        browser.close()

    report = {'url': url, 'checks': checks, 'errors': errors,
              'axe_version': next(iter(accessibility.values()))['testEngine']['version'] if accessibility else None,
              'axe_violations': {name: value['violations'] for name, value in accessibility.items()}}
    (output / 'qa.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': sum(checks.values()), 'total': len(checks),
                      'failed': [name for name, value in checks.items() if not value],
                      'axe_violations': {name: [x['id'] for x in value['violations']]
                                         for name, value in accessibility.items() if value['violations']}, 'errors': errors},
                     ensure_ascii=False, indent=2))
    return all(checks.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8787')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--axe', type=Path, help='Local axe.min.js; omit to skip automated axe checks')
    parser.add_argument('--browser-executable', help='Optional local Chromium executable for QA')
    args = parser.parse_args()
    passed = audit(args.url, args.output, args.axe.read_text() if args.axe else None, args.browser_executable)
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
