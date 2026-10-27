"""Real-browser proof (Chromium + Playwright) that a seller composes a FREE nested layout with the Design Studio's own buttons.

Scenarios A-F of the Visual Layout Composer mission. Nothing here calls the mutation service or the ORM while the Studio works: every change is
made by clicking the real controls (rail «ردیف ساده», the canvas chips, the toolbar «چیدمان» menu, the layers tree, the Group inspector, the
resize handles, the real Undo / Redo / «انتشار» buttons), and every assertion reads what the seller sees - the Preview iframe, the Studio's own
panels, then the PUBLISHED page at desktop and phone widths.

Opt-in: ``SFB_BROWSER_TESTS=1 DJANGO_SETTINGS_MODULE=shop_core.settings_browser_tests python manage.py test apps.storefront_builder.tests.test_v5_composer_browser``
(isolated ``DJANGO_MEDIA_ROOT``). Screenshots: ``SFB_SCREENSHOT_DIR``."""

import os
import unittest

from . import test_v5_studio_composition_browser as _studio_tests

_Base = _studio_tests.StudioCompositionBrowserTests

CELL = ".rcontainer-cell[data-cell-id]"

#: leaf cells (cells that hold no nested Group) of the whole Preview, in document order, with their share and their container
LEAVES_JS = """()=>[...document.querySelectorAll('.rcontainer-cell[data-cell-id]')].filter(c=>!c.querySelector(':scope > .rgroup, :scope > .rcontainer'))
  .map(c=>({id:Number(c.dataset.cellId), container:Number(c.dataset.containerId)}))"""

TREE_JS = """()=>{const walk=(c)=>({id:Number(c.dataset.containerId), axis:c.dataset.axis||'horizontal',
  spans:[...c.querySelectorAll(':scope > .rcontainer-cell')].map(e=>Number(e.style.getPropertyValue('--cell-span'))),
  kids:[...c.querySelectorAll(':scope > .rcontainer-cell > .rcontainer, :scope > .rcontainer-cell > .rgroup > .rcontainer')].map(walk)});
  return [...document.querySelectorAll('.sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup > .rcontainer')].map(walk)}"""


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class ComposerBrowserTests(_Base):
    pass


# the studio module's own tests must not run again here
for _name in [n for n in dir(_Base) if n.startswith("test")]:
    setattr(ComposerBrowserTests, _name, None)


class _Steps:
    """Seller gestures on the Studio (mixed into the test class below)."""

    def add_simple_row(self, page):
        """The rail's «ردیف ساده»; returns how many leaf cells the page had before (our row's leaves come after them)."""
        before = self.leaf_count(page)
        page.click('[data-rastisi-action="composer-add-row"]')
        self._until(page, f"()=>[...document.querySelectorAll('.rcontainer-cell[data-cell-id]')].length >= {before + 1}", "the simple row")
        page.wait_for_timeout(1200)
        return before

    def trace(self, page):
        if os.environ.get("SFB_DEBUG"):
            import sys
            page.on("console", lambda m: print("CONSOLE", m.text[:300], file=sys.stderr) if m.text.startswith(("SELECT", "CLICK", "BIND")) else None)
            page.evaluate("window.__cmpTrace=1")

    def settle(self, page, seconds=25):
        """Wait until the Preview iframe has stopped being swapped (a refreshed twin frame replaces the old one a moment after a write)."""
        mark = "()=>{const f=document.getElementById('r4PreviewFrame'); if(!f || RastiSiR4.previewRefreshBusy()) return null; if(!f.__m) f.__m=Math.random(); return f.__m+':'+(f.contentDocument&&f.contentDocument.readyState)}"
        import time
        end = time.time() + seconds
        last = None
        stable = 0
        while time.time() < end:
            now = page.evaluate(mark)
            stable = stable + 1 if now == last and now and now.endswith("complete") else 0
            last = now
            if stable >= 4:
                return
            page.wait_for_timeout(350)
        self.fail("the Preview kept refreshing")

    def pick_leaf(self, page, index):
        """Hover the index-th leaf cell on the canvas and click its «select» chip - exactly what a seller does."""
        self._close_drawer(page)
        self.settle(page)
        frame = self._frame(page)
        leaf = frame.locator(CELL).filter(has_not=frame.locator(".rcontainer")).nth(index)
        leaf.scroll_into_view_if_needed()
        leaf.hover()
        page.wait_for_timeout(300)
        if os.environ.get("SFB_DEBUG"):
            self._shot(page, f"dbg_pick_{index}")
        if os.environ.get("SFB_DEBUG"):
            import sys
            print("chip", leaf.locator(":scope > .sfb-layout-chip--cell").evaluate("""e=>{const r=e.getBoundingClientRect(); const t=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
              return e.dataset.cellLayout+' rect='+[r.x,r.y,r.width,r.height].map(Math.round)+' top='+(t&&t.tagName+'.'+t.className+' '+(t.dataset.groupLayout||t.dataset.cellLayout||''))+' op='+getComputedStyle(e).opacity+' pe='+getComputedStyle(e).pointerEvents}"""), file=sys.stderr)
        leaf.locator(":scope > .sfb-layout-chip--cell").click(force=True)
        if os.environ.get("SFB_DEBUG"):
            import sys
            for _ in range(3):
                print("  sel", page.evaluate("()=>JSON.stringify(RastiSiR4.composer.selection())"), file=sys.stderr)
                page.wait_for_timeout(200)
        page.wait_for_selector("[data-cmp-toolbar]:not([hidden])", timeout=6000)
        page.wait_for_timeout(250)
        if os.environ.get("SFB_DEBUG"):
            import sys
            print("picked", index, page.evaluate("()=>JSON.stringify(RastiSiR4.composer.selection())"), file=sys.stderr)

    def split(self, page, axis, count):
        page.click('[data-cmp="layout"]')
        page.wait_for_selector("[data-cmp-menu]:not([hidden])", timeout=4000)
        page.click(f'[data-cmp-split="{axis}:{count}"]')
        # the split is done when the new Group is the selection (the Studio selects it once the refreshed Preview is in place)
        page.wait_for_function("()=>{const s=RastiSiR4.composer.selection(); return s && s.kind==='group'}", timeout=20000)
        page.wait_for_function("()=>RastiSiR4.pendingWrites===0", timeout=20000)
        page.wait_for_timeout(600)
        page.wait_for_selector("[data-cmp-toolbar]:not([hidden])", timeout=8000)
        self.dump(page, f"after {axis}:{count}")

    def leaf_count(self, page):
        self.settle(page)
        return len(self._frame(page).evaluate(LEAVES_JS))

    def dump(self, page, label):
        if os.environ.get("SFB_DEBUG"):
            import sys
            print(label, self._frame(page).evaluate(TREE_JS)[-1:], file=sys.stderr)
            print("   studio-tree", page.evaluate("()=>JSON.stringify(RastiSiR4.composer.tree().slice(-1).map(function w(g){return {id:g.id,axis:g.axis,cells:g.cells.map(c=>({id:c.id,span:c.span,g:c.group?w(c.group):null}))}}))"), file=sys.stderr)


@unittest.skipUnless(os.environ.get("SFB_BROWSER_TESTS") == "1", "browser test is opt-in: SFB_BROWSER_TESTS=1")
class ComposerScenarioTests(_Steps, ComposerBrowserTests):
    def test_a_free_nested_layout_of_at_least_eight_cells_is_built_with_the_studio_buttons(self):
        context, page = self._studio()
        if os.environ.get("SFB_DEBUG"):
            import sys
            page.on("console", lambda m: print("CONSOLE", m.text[:400], file=sys.stderr))
            page.evaluate("window.__cmpTrace=1")
            page.evaluate("""()=>{window.__t0=Date.now(); let last=null; setInterval(()=>{const f=document.getElementById('r4PreviewFrame'); if(!f) return; if(!f.__m) f.__m=Math.random().toString(36).slice(2,6); if(f.__m!==last){last=f.__m; console.log('FRAME '+f.__m+' t='+(Date.now()-window.__t0));}},50)}""")
        try:
            base = self.add_simple_row(page)
            self.assertEqual(self.leaf_count(page), base + 1)
            # 1) one empty cell -> three columns
            self.pick_leaf(page, base)
            self.split(page, "horizontal", 3)
            self.assertEqual(self.leaf_count(page), base + 3)
            # 2) the first column -> three stacked rows; 3) the middle of those -> two columns; and so on
            self.pick_leaf(page, base)
            self.split(page, "vertical", 3)
            self.assertEqual(self.leaf_count(page), base + 5)
            self.pick_leaf(page, base + 1)
            self.split(page, "horizontal", 2)
            self.assertEqual(self.leaf_count(page), base + 6)
            self.pick_leaf(page, base + 5)
            self.split(page, "vertical", 2)
            self.assertEqual(self.leaf_count(page), base + 7)
            self.pick_leaf(page, base + 6)
            self.split(page, "horizontal", 3)
            self.assertEqual(self.leaf_count(page), base + 9)
            tree = self._frame(page).evaluate(TREE_JS)
            self.assertGreaterEqual(len(tree), 1)
            self._shot(page, "composer_a_free_layout")
            self.assertEqual(self.errors, [])
        finally:
            context.close()


    def edit_group(self, page):
        """«ویرایش» on the selected Group's toolbar opens the Group inspector (the panel's settings tab)."""
        page.click('[data-cmp="edit"]')
        page.wait_for_selector('.rs-workspace:not([hidden]) #r4Inspector [data-cmp-ws] [data-cmp-text="title"]', timeout=10000)

    def open_section(self, page, title):
        # the group settings dialog is tabbed: «title» is a tab label here
        page.locator("#r4Inspector [data-cmp-wtab]", has_text=title).first.click()
        page.wait_for_timeout(200)

    def type_into(self, page, selector, text):
        field = page.locator(selector)
        field.click()
        field.fill(text)
        page.wait_for_timeout(500)

    def group_view(self, page, container_id):
        return self._frame(page).evaluate("""(id)=>{const c=document.querySelector('.rcontainer[data-container-id="'+id+'"]'); if(!c) return null;
          const g=c.closest('.rgroup'); const cs=g?getComputedStyle(g):null;
          return {framed:!!g, title:g&&g.querySelector('.rgroup-title')?g.querySelector('.rgroup-title').textContent.trim():'',
                  desc:g&&g.querySelector('.rgroup-description')?g.querySelector('.rgroup-description').textContent.trim():'',
                  bg:cs?cs.backgroundImage:'', pad:cs?cs.paddingTop:'', radius:cs?cs.borderTopLeftRadius:'', align:cs?cs.textAlign:'',
                  color:cs?cs.color:'', spans:[...c.querySelectorAll(':scope > .rcontainer-cell')].map(e=>Number(e.style.getPropertyValue('--cell-span')))}}""", container_id)

    def selected_group_id(self, page):
        return page.evaluate("()=>{const s=RastiSiR4.composer.selection(); return s && s.kind==='group' ? s.id : null}")

    def test_b_a_group_is_designed_independently_of_its_children(self):
        context, page = self._studio()
        self.trace(page)
        try:
            base = self.add_simple_row(page)
            self.pick_leaf(page, base)
            self.split(page, "horizontal", 2)
            parent = self.selected_group_id(page)
            self.assertTrue(parent)
            # the PARENT group: title, description, gradient background, centred text, padding and rounded corners
            self.edit_group(page)
            self.type_into(page, '[data-cmp-text="title"]', "مجموعهٔ پاییزی")
            self.type_into(page, '[data-cmp-text="description"]', "ویژه مشتریان وفادار")
            page.locator('[data-cmp-theme="3"]').click()                    # «برند»: gradient + brand text colours in one click
            page.wait_for_timeout(900)
            self.open_section(page, "رنگ و پس‌زمینه")
            self.assertEqual(page.locator("[data-cmp-bg-mode]").input_value(), "gradient")
            self.open_section(page, "متن و فونت")
            page.select_option('[data-cmp-choice="style:text_align"]', "center")
            self.open_section(page, "فاصله و حاشیه")
            page.locator('[data-cmp-int-num="style:pad"]').fill("28")
            page.locator('[data-cmp-int-num="style:radius"]').fill("26")
            self._until(page, f"""()=>{{const c=document.querySelector('.rcontainer[data-container-id="{parent}"]'); const g=c&&c.closest('.rgroup');
              return g && g.querySelector('.rgroup-title') && g.querySelector('.rgroup-title').textContent.trim()==='مجموعهٔ پاییزی' && getComputedStyle(g).paddingTop==='28px'
                && getComputedStyle(g).borderTopLeftRadius==='26px' && getComputedStyle(g).backgroundImage.includes('linear-gradient')}}""", "the parent group look")
            view = self.group_view(page, parent)
            self.assertEqual((view["title"], view["desc"], view["align"]), ("مجموعهٔ پاییزی", "ویژه مشتریان وفادار", "center"))
            # the CHILDREN: the first cell becomes its own group with another look; the parent's look is untouched
            self.settle(page)
            page.click("#r4Inspector [data-r4-inspector-close]")            # the big settings dialog is closed with its own button
            self.pick_leaf(page, base)
            self.split(page, "vertical", 2)
            child = self.selected_group_id(page)
            self.assertNotEqual(child, parent)
            self.edit_group(page)
            self.type_into(page, '[data-cmp-text="title"]', "کودک اول")
            self.open_section(page, "رنگ و پس‌زمینه")
            page.select_option("[data-cmp-bg-mode]", "color")
            page.wait_for_timeout(900)
            self.open_section(page, "محتوا و تم")
            page.locator('[data-cmp-theme="1"]').click()                    # «تیره»
            self._until(page, f"""()=>{{const c=document.querySelector('.rcontainer[data-container-id="{child}"]'); const g=c&&c.closest('.rgroup');
              return g && g.querySelector('.rgroup-title') && g.querySelector('.rgroup-title').textContent.trim()==='کودک اول'
                && getComputedStyle(g.querySelector('.rgroup-title')).color==='rgb(255, 255, 255)'}}""", "the child group look")
            parent_after = self.group_view(page, parent)
            child_view = self.group_view(page, child)
            self.assertEqual(parent_after["title"], "مجموعهٔ پاییزی")
            self.assertIn("linear-gradient", parent_after["bg"])
            self.assertEqual(child_view["title"], "کودک اول")
            self.assertNotIn("linear-gradient", child_view["bg"])
            self.assertNotEqual(parent_after["color"], child_view["color"])
            # an edited group is swapped as ONE frame: never wrapped again inside its own previous markup
            counts = self._frame(page).evaluate(f"()=>({{frames:document.querySelectorAll('.rgroup[data-group-id=\"{parent}\"]').length,"
                                                f"titles:document.querySelectorAll('.rgroup-title').length,"
                                                f"nested:!!document.querySelector('.rgroup[data-group-id=\"{parent}\"] .rcontainer-cell .rgroup[data-group-id=\"{child}\"]')}})")
            self.assertEqual(counts, {"frames": 1, "titles": 2, "nested": True})
            if os.environ.get("SFB_DEBUG"):
                import sys
                print("TITLES", self._frame(page).evaluate("()=>[...document.querySelectorAll('.rgroup')].map(g=>({id:g.dataset.groupId,t:(g.querySelector('.rgroup-title')||{}).textContent,h:Math.round(g.getBoundingClientRect().height),n:g.querySelectorAll('.rgroup-title').length}))"), file=sys.stderr)
            self._shot(page, "composer_b_group_design")
            self.assertEqual(self.errors, [])
        finally:
            context.close()

    # ------------------------------------------------------------------------------------------------------------ scenario C
    def spans_of(self, page, container_id):
        return self._frame(page).evaluate(
            "(id)=>{const c=document.querySelector('.rcontainer[data-container-id=\"'+id+'\"]'); return c?[...c.querySelectorAll(':scope > .rcontainer-cell')].map(e=>Number(e.style.getPropertyValue('--cell-span'))):null}",
            container_id)

    def widths_of(self, page, container_id, axis="w"):
        return self._frame(page).evaluate(
            "([id,axis])=>{const c=document.querySelector('.rcontainer[data-container-id=\"'+id+'\"]'); return [...c.querySelectorAll(':scope > .rcontainer-cell')].map(e=>Math.round(axis==='w'?e.getBoundingClientRect().width:e.getBoundingClientRect().height))}",
            [container_id, axis])

    def drag_handle(self, page, container_id, kind, dx=0, dy=0, index=0):
        """Drag a REAL resize handle of the given container (kind c = column boundary, r = row boundary) by (dx, dy) pixels."""
        self.settle(page)
        sel = f'[data-rs-handle="{kind}"][data-rs-container-id="{container_id}"][data-rs-index="{index}"]'
        handle = page.locator(sel)
        handle.wait_for(state="visible", timeout=10000)
        box = handle.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + dx, y + dy, steps=10)
        page.mouse.up()
        page.wait_for_function("()=>RastiSiR4.pendingWrites===0", timeout=20000)
        self.settle(page)

    def test_c_resizing_a_parent_keeps_the_children_proportions_and_survives_undo_refresh(self):
        context, page = self._studio()
        try:
            base = self.add_simple_row(page)
            self.pick_leaf(page, base)
            self.split(page, "horizontal", 2)
            parent = self.selected_group_id(page)
            self.pick_leaf(page, base)
            self.split(page, "horizontal", 2)
            child = self.selected_group_id(page)
            self.assertNotEqual(parent, child)
            self.assertEqual((self.spans_of(page, parent), self.spans_of(page, child)), ([6, 6], [6, 6]))
            before_w = self.widths_of(page, child)
            # 1) drag the PARENT's column handle: the first (right-hand) cell grows, its children keep 50 / 50
            self.drag_handle(page, parent, "c", dx=-170)
            parent_spans = self.spans_of(page, parent)
            self.assertEqual(sum(parent_spans), 12)
            self.assertGreater(parent_spans[0], 6)
            self.assertEqual(self.spans_of(page, child), [6, 6])
            after_w = self.widths_of(page, child)
            self.assertGreater(sum(after_w), sum(before_w) + 40)             # the child as a whole became wider ...
            self.assertAlmostEqual(after_w[0] / after_w[1], 1.0, delta=0.08)  # ... and kept its own 1 : 1 proportion
            # 2) drag the CHILD's own handle: only the child's shares change
            self.drag_handle(page, child, "c", dx=-60)
            child_spans = self.spans_of(page, child)
            self.assertNotEqual(child_spans, [6, 6])
            self.assertEqual(self.spans_of(page, parent), parent_spans)
            self._shot(page, "composer_c_resize")
            # 3) the real Undo restores the child's shares, Redo brings them back (container ids change on restore: found by structure)
            find_child = "(()=>{const k=[...document.querySelectorAll('.rcontainer--nested')].find(c=>c.querySelectorAll(':scope > .rcontainer-cell').length===2); return k})()"
            read = f"()=>{{const k={find_child}; return k?[...k.querySelectorAll(':scope > .rcontainer-cell')].map(e=>Number(e.style.getPropertyValue('--cell-span'))).join():null}}"
            page.click("#r4UndoButton")
            self._until(page, f"()=>({read[3:]})()==='6,6'" if False else f"()=>{{const k={find_child}; return !!k && [...k.querySelectorAll(':scope > .rcontainer-cell')].map(e=>Number(e.style.getPropertyValue('--cell-span'))).join()==='6,6'}}", "Undo of the child resize")
            self.settle(page)
            page.click("#r4RedoButton")
            self._until(page, f"()=>{{const k={find_child}; return !!k && [...k.querySelectorAll(':scope > .rcontainer-cell')].map(e=>Number(e.style.getPropertyValue('--cell-span'))).join()==='{','.join(map(str, child_spans))}'}}", "Redo of the child resize")
            self.settle(page)
            # 4) a vertical split: its row boundaries change the HEIGHT shares
            self.pick_leaf(page, base + 2)
            self.split(page, "vertical", 3)
            rows = self.selected_group_id(page)
            self.assertEqual(self.spans_of(page, rows), [4, 4, 4])
            heights = self.widths_of(page, rows, "h")
            self.drag_handle(page, rows, "r", dy=90, index=0)
            row_spans = self.spans_of(page, rows)
            self.assertEqual(sum(row_spans), 12)
            self.assertGreater(row_spans[0], 4)
            self.assertGreater(self.widths_of(page, rows, "h")[0], heights[0])
            # 5) refresh the whole Studio: every share is still there (saved in the Draft)
            page.wait_for_timeout(600)
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#r4PreviewFrame")
            page.wait_for_timeout(1500)
            self._frame(page)
            self.settle(page)
            saved = self._frame(page).evaluate("""()=>[...document.querySelectorAll('.rcontainer--nested, .sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup > .rcontainer')]
              .map(c=>[...c.querySelectorAll(':scope > .rcontainer-cell')].map(e=>Number(e.style.getPropertyValue('--cell-span'))).join('-'))""")
            self.assertIn("-".join(map(str, row_spans)).replace("-", "-"), [x.replace(",", "-") for x in saved] + saved)
            self.assertIn("-".join(map(str, parent_spans)), saved)
            self.assertIn("-".join(map(str, child_spans)), saved)
            self.assertEqual(self.errors, [])
        finally:
            context.close()

    # ------------------------------------------------------------------------------------------------------------ scenario D
    def add_component(self, page, key):
        """«ویرایش» on an EMPTY selected cell opens the real component library for that cell; one click on a card adds the real R4 section."""
        page.click('[data-cmp="edit"]')
        page.wait_for_selector('[data-rastisi-action="cell-add"]', timeout=10000)
        page.locator(f'[data-rastisi-action="cell-add"][data-rs-library-key="{key}"]').first.click()
        page.wait_for_function("()=>RastiSiR4.pendingWrites===0", timeout=20000)
        self._until(page, f"()=>!!document.querySelector('.rsec[data-section-key=\"{key}\"]')", f"the {key} component in the Preview")
        self.settle(page)

    def library_keys(self, page):
        page.click('[data-cmp="edit"]')
        page.wait_for_selector('[data-rastisi-action="cell-add"]', timeout=10000)
        keys = page.evaluate("()=>[...document.querySelectorAll('[data-rastisi-action=\"cell-add\"][data-rs-library-key]')].map(e=>e.dataset.rsLibraryKey)")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return keys

    def test_d_real_registry_components_fill_a_free_layout_and_survive_re_layout(self):
        from apps.storefront_builder import section_registry

        context, page = self._studio()
        try:
            base = self.add_simple_row(page)
            self.pick_leaf(page, base)
            self.split(page, "horizontal", 2)
            # the library the seller sees offers the registry's components (every one the page may legally hold)
            self.pick_leaf(page, base)
            offered = self.library_keys(page)
            self.assertGreaterEqual(len(offered), 20)
            self.assertTrue(set(offered) <= set(section_registry.SECTION_REGISTRY), set(offered) - set(section_registry.SECTION_REGISTRY))
            for key in ("rich_text", "linked_image", "product_section", "multi_banner", "category_grid"):
                self.assertIn(key, offered)
            # 1) a text block (rich_text) in the first cell and a REAL product shelf in the second
            self.pick_leaf(page, base)
            self.add_component(page, "rich_text")
            self.pick_leaf(page, base + 1)
            self.add_component(page, "product_section")
            shelf = self._frame(page).evaluate("()=>{const s=document.querySelector('.rsec[data-section-key=\"product_section\"]'); return s?{cards:s.querySelectorAll('.pcard, [data-product-id], .product-card').length, h:Math.round(s.getBoundingClientRect().height)}:null}")
            self.assertIsNotNone(shelf)
            self.assertGreater(shelf["h"], 120)
            # 2) split the cell that HOLDS the text block: its content stays (first new cell), the other new cells take a media image and a banner
            self.pick_leaf(page, base)
            self.split(page, "vertical", 2)
            kept = self._frame(page).evaluate("()=>{const row=[...document.querySelectorAll('.sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup')].pop(); return [...row.querySelectorAll('.rcontainer-cell[data-cell-id]')].filter(c=>!c.querySelector('.rcontainer-cell')&&c.querySelector(':scope > .rsec[data-section-key=\"rich_text\"]')).length}")
            self.assertEqual(kept, 1, "the text block must survive the split inside the first new cell")
            self.pick_leaf(page, base + 1)
            self.split(page, "horizontal", 2)                                # the empty second cell becomes two empty cells
            self.pick_leaf(page, base + 1)
            self.add_component(page, "linked_image")
            self.pick_leaf(page, base + 2)
            self.add_component(page, "multi_banner")
            keys = self._frame(page).evaluate("()=>[...document.querySelectorAll('.rsec[data-section-key]')].map(e=>e.dataset.sectionKey)")
            for key in ("rich_text", "linked_image", "product_section", "multi_banner"):
                self.assertIn(key, keys)
            # 3) split the cell that holds the product shelf: it stays in the first new cell, the second takes a fifth component
            self.pick_leaf(page, base + 3)
            self.split(page, "vertical", 2)
            self.pick_leaf(page, base + 4)
            self.add_component(page, "category_grid")
            kept_shelf = self._frame(page).evaluate("()=>{const row=[...document.querySelectorAll('.sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup')].pop(); return [...row.querySelectorAll('.rcontainer-cell[data-cell-id]')].filter(c=>!c.querySelector('.rcontainer-cell')&&c.querySelector(':scope > .rsec[data-section-key=\"product_section\"]')).length}")
            self.assertEqual(kept_shelf, 1)
            # 4) re-lay out the TOP group (select parents until the row, then three columns): every component is kept
            before = sorted(self._frame(page).evaluate("()=>{const row=[...document.querySelectorAll('.sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup')].pop(); return [...row.querySelectorAll('.rsec[data-section-id]')].map(e=>Number(e.dataset.sectionId))}"))
            for _ in range(3):
                page.click('[data-cmp="parent"]')
                page.wait_for_timeout(300)
            self.assertTrue(self.selected_group_id(page))
            self.split(page, "horizontal", 3)
            after = sorted(self._frame(page).evaluate("()=>{const row=[...document.querySelectorAll('.sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup')].pop(); return [...row.querySelectorAll('.rsec[data-section-id]')].map(e=>Number(e.dataset.sectionId))}"))
            self.assertEqual(before, after, "re-laying out a group must keep every component")
            self._shot(page, "composer_d_real_components")
            self.assertEqual(self.errors, [])
        finally:
            context.close()

    # ------------------------------------------------------------------------------------------------------------ scenario E
    PURCHASE_JS = """()=>({forms:[...document.querySelectorAll('form')].filter(f=>f.querySelector('.pdp-actions')).length,
        selectors:document.querySelectorAll('[x-data*="variantSelector"]').length, actions:document.querySelectorAll('.pdp-actions').length,
        satc:document.querySelectorAll('.pdp-satc').length, price:document.querySelectorAll('.pricebox .now').length,
        qty:document.querySelectorAll('input[name=quantity]').length})"""

    def test_e_header_and_footer_are_on_the_canvas_and_the_product_page_keeps_one_purchase_flow(self):
        from django.urls import reverse

        context, page = self._studio()
        try:
            # 1) Header -> Main -> Footer are all on the canvas, and clicking them opens the REAL header / footer editors
            order = self._frame(page).evaluate("()=>{const h=document.querySelector('header'), m=document.querySelector('.sfb-preview-sections'), f=document.querySelector('footer');"
                                               "return [h.getBoundingClientRect().top, m.getBoundingClientRect().top, f.getBoundingClientRect().top]}")
            self.assertLess(order[0], order[1])
            self.assertLess(order[1], order[2])
            frame = self._frame(page)
            frame.locator("footer").first.click(position={"x": 6, "y": 6}, force=True)
            page.wait_for_function("()=>{const d=document.getElementById('rsGlobalFooter'); return !!d && d.open}", timeout=10000)
            self.assertEqual(page.evaluate("()=>document.querySelector('.rs-studio').dataset.rsMode"), "global")
            self._close_drawer(page)
            frame = self._frame(page)
            frame.locator("header").first.click(position={"x": 6, "y": 6}, force=True)
            page.wait_for_function("()=>{const d=document.getElementById('rsGlobalHeader'); return !!d && d.open}", timeout=10000)
            self._close_drawer(page)
            # the layers tree lists the same three regions in the same order and opens the same editors
            page.click('[data-rastisi-action="composer-panel"]')
            page.wait_for_selector('[data-cmp-node="header:0"]')
            nodes = page.evaluate("()=>[...document.querySelectorAll('[data-cmp-panel] [data-cmp-node]')].map(e=>e.dataset.cmpNode.split(':')[0])")
            self.assertEqual((nodes[0], nodes[-1]), ("header", "footer"))
            page.click('[data-cmp-node="footer:0"]')
            page.wait_for_function("()=>{const d=document.getElementById('rsGlobalFooter'); return !!d && d.open}", timeout=10000)
            self._close_drawer(page)
        finally:
            context.close()

        # 2) the product page: a free row is added, split and filled; the purchase flow stays ONE flow
        context, page = self._studio("product_detail")
        try:
            before = self._frame(page).evaluate(self.PURCHASE_JS)
            self.assertEqual((before["forms"], before["selectors"], before["satc"] <= 1), (1, 1, True))
            base = self.add_simple_row(page)
            self.pick_leaf(page, base)
            self.split(page, "horizontal", 2)
            self.pick_leaf(page, base)
            self.add_component(page, "rich_text")
            self.pick_leaf(page, base + 1)
            self.add_component(page, "faq")
            during = self._frame(page).evaluate(self.PURCHASE_JS)
            self.assertEqual(during, before, "composing around the buy box must not duplicate or remove any purchase control")
            self._shot(page, "composer_e_pdp")
            page.wait_for_timeout(800)
            self._publish(page)
        finally:
            context.close()
        path = reverse("catalog:product-detail", args=["parity-0"])
        for width in (1440, 390):
            ctx, public = self._public(path, width, 900)
            try:
                facts = public.evaluate(self.PURCHASE_JS)
                self.assertEqual((facts["forms"], facts["selectors"]), (1, 1))
                self.assertEqual(public.evaluate("()=>document.querySelectorAll('.rgroup, .rcontainer--nested').length >= 0"), True)
                self.assertGreater(public.evaluate("()=>document.querySelectorAll('.rcontainer-cell').length"), 2)
                self.assertLessEqual(public.evaluate("()=>document.documentElement.scrollWidth - innerWidth"), 0)
                if width == 1440:
                    # the real add-to-cart button still adds the real product, and the cart and checkout pages work
                    public.locator(".pdp-actions button[type=submit]").first.click()
                    public.wait_for_timeout(2500)
                    public.goto(f"{self.public_base}{reverse('cart:detail')}", wait_until="networkidle")
                    self.assertGreater(public.locator("body").inner_text().count("کالا"), 0)
                    self.assertTrue(public.locator("a[href*='checkout']").count() >= 1, "the cart must still lead to checkout")
                    self._shot(public, "composer_e_published_cart")
            finally:
                ctx.close()

    # ------------------------------------------------------------------------------------------------------------ scenario F
    def row_snapshot(self, page):
        """The last page row as the seller sees it: nested structure, titles and the components it holds."""
        return self._frame(page).evaluate("""()=>{const row=[...document.querySelectorAll('.sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup')].pop();
          if(!row) return null; return {titles:[...row.querySelectorAll('.rgroup-title')].map(e=>e.textContent.trim()),
            cells:row.querySelectorAll('.rcontainer-cell').length, keys:[...row.querySelectorAll('.rsec[data-section-key]')].map(e=>e.dataset.sectionKey)}}""")

    def test_f_build_edit_refresh_undo_redo_draft_preview_and_publish(self):
        context, page = self._studio()
        try:
            base = self.add_simple_row(page)
            self.pick_leaf(page, base)
            self.split(page, "horizontal", 2)
            self.edit_group(page)
            self.type_into(page, '[data-cmp-text="title"]', "ویترین بهاره")
            page.locator('[data-cmp-theme="2"]').click()
            self._until(page, "()=>[...document.querySelectorAll('.rgroup-title')].some(e=>e.textContent.trim()==='ویترین بهاره')", "the group title")
            page.click("#r4Inspector [data-r4-inspector-close]")
            self.settle(page)
            self.pick_leaf(page, base)
            self.add_component(page, "rich_text")
            self.pick_leaf(page, base + 1)
            self.add_component(page, "product_section")
            built = self.row_snapshot(page)
            self.assertEqual((built["titles"], built["cells"]), (["ویترین بهاره"], 2))
            self.assertEqual(sorted(built["keys"]), ["product_section", "rich_text"])
            page.wait_for_timeout(900)
            # refresh the whole Studio: the Draft kept everything
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#r4PreviewFrame")
            page.wait_for_timeout(1500)
            self._frame(page)
            self.settle(page)
            self.assertEqual(self.row_snapshot(page), built)
            # the real Undo takes the LAST edit (the shelf) away, Redo brings it back
            page.click("#r4UndoButton")
            self._until(page, "()=>{const r=[...document.querySelectorAll('.sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup')].pop(); return r && !r.querySelector('.rsec[data-section-key=\"product_section\"]')}", "Undo")
            self.settle(page)
            page.click("#r4RedoButton")
            self._until(page, "()=>{const r=[...document.querySelectorAll('.sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup')].pop(); return r && !!r.querySelector('.rsec[data-section-key=\"product_section\"]')}", "Redo")
            self.settle(page)
            # delete with content asks first; cancelling changes nothing, confirming removes it, Undo gives it all back
            page.click('[data-rastisi-action="composer-panel"]')
            page.locator('[data-cmp-panel] [data-cmp-node^="group:"]').last.click()
            page.wait_for_selector("[data-cmp-toolbar]:not([hidden])")
            page.click('[data-cmp="remove"]')
            page.wait_for_selector(".rs-cmp-confirm")
            page.click("[data-cmp-no]")
            self.assertEqual(self.row_snapshot(page), built)
            page.click('[data-cmp="remove"]')
            page.wait_for_selector(".rs-cmp-confirm")
            page.click("[data-cmp-yes]")
            page.wait_for_function("()=>RastiSiR4.pendingWrites===0", timeout=20000)
            self.settle(page)
            self.assertNotEqual(self.row_snapshot(page), built)
            page.click("#r4UndoButton")
            self._until(page, "()=>[...document.querySelectorAll('.rgroup-title')].some(e=>e.textContent.trim()==='ویترین بهاره')", "Undo of the delete")
            self.settle(page)
            self.assertEqual(self.row_snapshot(page), built)
            # «پیش‌نمایش» (the customer's view of the saved Draft) shows it; the published page does not yet
            draft = context.new_page()
            draft.goto(f"{self.base}/admin-portal/storefront-builder/draft-preview/", wait_until="networkidle")
            self.assertGreaterEqual(draft.locator(".rgroup-title", has_text="ویترین بهاره").count(), 1)
            draft.close()
            ctx, before = self._public("/", 1440)
            try:
                self.assertEqual(before.locator(".rgroup-title", has_text="ویترین بهاره").count(), 0)
            finally:
                ctx.close()
            page.wait_for_timeout(800)
            # screenshot-only copy for the text block (the Studio is idle; every assertion above and below reads what the seller sees)
            from apps.storefront_builder.models import StorefrontSection

            text = StorefrontSection.objects.filter(section_key="rich_text", page__version__status="draft").order_by("-id").first()
            text.settings = {**(text.settings or {}), "body_html": "<h3>پیشنهاد فصل</h3><p>مجموعهٔ تازه با ارسال سریع و بستهبندی هدیه.</p>", "design": {"align": "center", "valign": "center", "min_height": 220}}
            text.save(update_fields=["settings"])
            self._publish(page)
            self.assertEqual(self.errors, [])
        finally:
            context.close()
        for width, name in ((1440, "desktop"), (390, "mobile")):
            ctx, public = self._public("/", width, 900)
            try:
                facts = public.evaluate("""()=>{const g=[...document.querySelectorAll('.rgroup')].find(e=>e.querySelector('.rgroup-title')&&e.querySelector('.rgroup-title').textContent.trim()==='ویترین بهاره');
                  if(!g) return null; const cells=[...g.querySelectorAll(':scope > .rcontainer > .rcontainer-cell')].map(c=>Math.round(c.getBoundingClientRect().width));
                  return {cells, gw:Math.round(g.getBoundingClientRect().width), vw:innerWidth, overflow:document.documentElement.scrollWidth-innerWidth,
                          chrome:document.querySelectorAll('.sfb-layout-chip,.sfb-builder-group,.sfb-builder-container').length}}""")
                self.assertIsNotNone(facts, f"{name}: the published page lost the group")
                self.assertLessEqual(facts["overflow"], 0)
                self.assertEqual(facts["chrome"], 0, "builder chrome must never reach the storefront")
                if width == 1440:
                    self.assertEqual(len(facts["cells"]), 2)
                    self.assertLess(max(facts["cells"]) / min(facts["cells"]), 1.4)
                else:
                    self.assertGreater(min(facts["cells"]), facts["vw"] * 0.7, "on a phone the two cells stack at full width")
                public.locator(".rgroup", has=public.locator(".rgroup-title", has_text="ویترین بهاره")).first.scroll_into_view_if_needed()
                self._shot(public, f"composer_f_published_{name}")
            finally:
                ctx.close()


    # ------------------------------------------------------------------------------------------------------------ scenario G (QA fixes)
    def visible_toolbars(self, page):
        return page.evaluate("()=>[...document.querySelectorAll('[data-cmp-toolbar], [data-rs-sel-toolbar]')].filter(e=>!e.hidden && e.getClientRects().length).length")

    def toolbar_name(self, page):
        return page.locator("[data-cmp-toolbar] [data-cmp-name] b").first.inner_text()

    def test_g_one_toolbar_with_the_element_name_real_section_editing_group_dialog_and_narrow_shelves(self):
        context, page = self._studio()
        self.trace(page)
        try:
            base = self.add_simple_row(page)
            self.pick_leaf(page, base)
            self.split(page, "horizontal", 3)
            # the row's own name is in the toolbar (no title yet -> «ردیف N»)
            self.assertRegex(self.toolbar_name(page), r"^ردیف ")
            self.assertEqual(self.visible_toolbars(page), 1)
            # a real product shelf in the first (narrow, one third) cell
            self.pick_leaf(page, base)
            self.assertRegex(self.toolbar_name(page), r"^ستون ۱ از ۳")
            self.add_component(page, "product_section")
            self.settle(page)
            # 1) a click on a product card selects the SECTION (no navigation); the toolbar shows its registry name
            frame = self._frame(page)
            url_before = frame.url
            shelf = frame.locator('.rcontainer-cell[data-cw] .rsec[data-section-key="product_section"] .pcard a[href]').first
            shelf.scroll_into_view_if_needed()
            shelf.click(force=True)                      # the real mouse lands on whatever is on top of the card (its quick-add button)
            page.wait_for_selector("[data-cmp-toolbar]:not([hidden]) [data-cmp-name]", timeout=8000)
            registry_label = page.evaluate("()=>{const t=RastiSiR4.composer.tree(); let out=null; const w=(g)=>g.cells.forEach(c=>{c.blocks.forEach(b=>{if(b.key==='product_section') out=b.label}); if(c.group) w(c.group)}); t.forEach(w); return out}")
            self.assertEqual(self.toolbar_name(page), registry_label)
            self.assertEqual(self._frame(page).url, url_before, "a click in design mode must not navigate the seller away")
            self.assertEqual(self.visible_toolbars(page), 1, "exactly one toolbar for a selected Section")
            self._shot(page, "composer_g_section_toolbar")
            # 2) «ویرایش» opens the real Section inspector of that shelf
            page.click('[data-cmp="edit"]')
            page.wait_for_selector("#r4Inspector [data-r4-tab]", timeout=15000)
            self.assertEqual(page.locator("#r4Inspector [data-cmp-ws]").count(), 0)
            page.keyboard.press("Escape")
            page.wait_for_function("()=>!RastiSiR4.inspectorOpen", timeout=10000)
            self.settle(page)
            # 3) «چیدمان» hands over to the parent cell: still exactly one toolbar, now named after the cell, content untouched
            frame = self._frame(page)
            frame.locator('.rcontainer-cell[data-cw] .rsec[data-section-key="product_section"] .pcard a[href]').first.click(force=True)
            page.wait_for_selector("[data-cmp-toolbar] [data-cmp=\"layout\"]")
            page.click('[data-cmp="layout"]')
            page.wait_for_selector("[data-cmp-menu]:not([hidden])")
            self.assertRegex(self.toolbar_name(page), r"^ستون ۱ از ۳")
            self.assertEqual(self.visible_toolbars(page), 1)
            self.assertIsNone(page.evaluate("()=>RastiSiR4.studio.selectedId()"))
            page.keyboard.press("Escape")
            # 4) two Sections in one cell: «ویرایش» asks which one instead of guessing
            page.locator('[data-cmp="close"]').click()
            frame = self._frame(page)
            frame.locator('.sfb-cell-add-more').last.scroll_into_view_if_needed()
            frame.locator('.sfb-cell-add-more').last.click(force=True)
            page.wait_for_selector('[data-rastisi-action="cell-add"]', timeout=10000)
            page.locator('[data-rastisi-action="cell-add"][data-rs-library-key="rich_text"]').first.click()
            page.wait_for_function("()=>RastiSiR4.pendingWrites===0", timeout=20000)
            self.settle(page)
            self.pick_leaf(page, base)
            page.click('[data-cmp="edit"]')
            page.wait_for_selector("[data-cmp-menu] [data-cmp-pick]", timeout=6000)
            self.assertGreaterEqual(page.locator("[data-cmp-menu] [data-cmp-pick]").count(), 2)
            self.assertEqual(page.locator("#r4Inspector [data-r4-tab]").count(), 0, "nothing may be opened before the seller chooses")
            page.keyboard.press("Escape")
            page.locator('[data-cmp="close"]').click()
            # 5) the Group settings are a big workspace dialog (same shell as a Section's)
            self.settle(page)
            page.click('[data-rastisi-action="composer-panel"]')
            page.locator('[data-cmp-panel] [data-cmp-node^="group:"]').first.click()
            page.click('[data-cmp="edit"]')
            page.wait_for_selector('.rs-workspace:not([hidden]) #r4Inspector [data-cmp-ws]', timeout=10000)
            self.assertEqual(page.evaluate("()=>document.querySelector('[data-rs-workspace-dialog]').getAttribute('aria-label')"), "تنظیمات گروه")
            size = page.evaluate("()=>{const r=document.querySelector('[data-rs-workspace-dialog]').getBoundingClientRect(); return [r.width, r.height, innerWidth, innerHeight]}")
            self.assertGreater(size[0], size[2] * 0.6)
            self.assertGreater(size[1], size[3] * 0.6)
            self.type_into(page, '[data-cmp-text="title"]', "پیشنهادهای ویژه")
            self._shot(page, "composer_g_group_dialog")
            self.open_section(page, "متن و فونت")
            page.select_option('[data-cmp-choice="style:font"]', index=1)
            self.open_section(page, "رنگ و پس‌زمینه")
            page.select_option("[data-cmp-bg-mode]", "gradient")
            page.wait_for_timeout(900)
            self._until(page, "()=>[...document.querySelectorAll('.rgroup-title')].some(e=>e.textContent.trim()==='پیشنهادهای ویژه')", "the group title from the dialog")
            page.keyboard.press("Escape")
            page.wait_for_function("()=>!RastiSiR4.inspectorOpen", timeout=10000)
            self.settle(page)
            # the toolbar name follows the new title without any refresh
            page.locator('[data-cmp-panel] [data-cmp-node^="group:"]').first.click()
            page.wait_for_selector("[data-cmp-toolbar] [data-cmp-name]")
            self.assertEqual(self.toolbar_name(page), "ردیف: پیشنهادهای ویژه")
            self.assertEqual(self.visible_toolbars(page), 1)
            self.assertIn("پیشنهادهای ویژه", page.locator("[data-cmp-toolbar] [data-cmp-name]").first.get_attribute("title"))
            # Undo / Redo / Refresh keep what the dialog saved
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#r4PreviewFrame")
            page.wait_for_timeout(1500)
            self._frame(page)
            self.settle(page)
            self._until(page, "()=>[...document.querySelectorAll('.rgroup-title')].some(e=>e.textContent.trim()==='پیشنهادهای ویژه')", "the title after a refresh")
            # 6) the shelf in the narrow cell shows fewer columns and stays readable; an ordinary full-width row is unchanged
            cards = self._frame(page).evaluate("""()=>{const row=[...document.querySelectorAll('.sfb-preview-sections > .rcontainer, .sfb-preview-sections > .rgroup')].pop();
              const cell=row.querySelector('.rcontainer-cell[data-cw] .rsec[data-section-key="product_section"]'); const host=cell&&cell.closest('.rcontainer-cell');
              const list=host&&host.querySelector('.pcarousel, .grid'); const card=host&&host.querySelector('.pcard');
              const other=[...document.querySelectorAll('.sfb-preview-sections > .rcontainer > .rcontainer-cell:not([data-cw]) .pcarousel')][0];
              return host?{cw:host.dataset.cw, cols:getComputedStyle(list).getPropertyValue('--cols-desktop').trim(), card:Math.round(card.getBoundingClientRect().width), cell:Math.round(host.getBoundingClientRect().width),
                           ordinary:other?getComputedStyle(other).getPropertyValue('--cols-desktop').trim():null}:null}""")
            self.assertIsNotNone(cards, "the shelf must sit in a Group cell")
            self.assertEqual(cards["cw"], "2")
            self.assertEqual(cards["cols"], "2")
            self.assertGreater(cards["card"], cards["cell"] * 0.38, cards)
            if cards["ordinary"] is not None:
                self.assertNotIn(cards["ordinary"], ("1",), "an ordinary row keeps the columns its own settings give")
            self._shot(page, "composer_g_toolbar_dialog_narrow")
            page.wait_for_timeout(800)
            self._publish(page)
            self.assertEqual(self.errors, [])
        finally:
            context.close()
        for width in (1440, 390):
            ctx, public = self._public("/", width, 900)
            try:
                facts = public.evaluate("""()=>{const g=[...document.querySelectorAll('.rgroup')].find(e=>e.querySelector('.rgroup-title')&&e.querySelector('.rgroup-title').textContent.trim()==='پیشنهادهای ویژه');
                  if(!g) return null; const a=g.querySelectorAll('.pcard a[href]'); const card=g.querySelector('.pcard');
                  return {links:a.length, href:a.length?a[0].getAttribute('href'):'', card:card?Math.round(card.getBoundingClientRect().width):0, overflow:document.documentElement.scrollWidth-innerWidth,
                          chrome:document.querySelectorAll('.sfb-layout-chip,[data-cmp-name],.rs-cmp-toolbar').length}}""")
                self.assertIsNotNone(facts)
                self.assertGreater(facts["links"], 0, "product links stay real links on the published storefront")
                self.assertIn("/products/", facts["href"])
                self.assertGreater(facts["card"], 120)
                self.assertLessEqual(facts["overflow"], 0)
                self.assertEqual(facts["chrome"], 0)
                if width == 1440:
                    self._shot(public, "composer_g_published_desktop")
                else:
                    self._shot(public, "composer_g_published_mobile")
            finally:
                ctx.close()


    # ------------------------------------------------------------------------------------------------------------ scenario H (Windows QA: «محصولات ویژه»)
    def test_h_featured_products_inside_a_group_opens_its_real_inspector_and_failures_are_visible(self):
        context, page = self._studio()
        try:
            base = self.add_simple_row(page)
            self.pick_leaf(page, base)
            self.split(page, "horizontal", 2)
            self.pick_leaf(page, base)
            self.add_component(page, "featured_products")
            cards = lambda: self._frame(page).evaluate(
                "()=>{const s=document.querySelector('.rcontainer-cell[data-cw] .rsec[data-section-key=\"featured_products\"]'); return s?s.querySelectorAll('.pcard').length:-1}")
            before = cards()
            self.assertGreater(before, 2)
            # a failed request is NOT silent: the seller reads a Persian message (simulated 404 on the real endpoint)
            page.route("**/sections/*/inspector/", lambda route: route.fulfill(status=404, body="nope"))
            self._frame(page).locator('.rcontainer-cell[data-cw] .rsec[data-section-key="featured_products"] .pcard').first.click(force=True)
            page.wait_for_selector("[data-cmp-toolbar]:not([hidden]) [data-cmp-name]")
            page.click('[data-cmp="edit"]')
            page.wait_for_function("()=>{const t=document.querySelector('.toast, [data-rs-toast], .rs-toast'); return !!t && /تنظیمات این بخش باز نشد/.test(t.textContent)}", timeout=8000)
            page.unroute("**/sections/*/inspector/")
            page.wait_for_timeout(4200)
            # the real endpoint: the large workspace opens with the product-count field; the new value is saved and changes the shelf
            page.click('[data-cmp="edit"]')
            page.wait_for_selector("#r4Inspector [data-r4-field-key=\"item_limit\"]", timeout=15000)
            self.assertEqual(page.locator("#r4Inspector [data-cmp-ws]").count(), 0)
            field = page.locator('#r4Inspector [data-r4-field-key="item_limit"] input').first
            field.fill("3")
            field.press("Tab")
            self._until(page, "()=>{const s=document.querySelector('.rcontainer-cell[data-cw] .rsec[data-section-key=\"featured_products\"]'); return s && s.querySelectorAll('.pcard').length===3}", "three products after the change")
            page.keyboard.press("Escape")
            page.wait_for_function("()=>!RastiSiR4.inspectorOpen", timeout=10000)
            page.wait_for_timeout(900)
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#r4PreviewFrame")
            page.wait_for_timeout(1500)
            self._frame(page)
            self.settle(page)
            self.assertEqual(cards(), 3, "the saved limit survives a refresh")
            self._shot(page, "composer_h_featured_inspector")
        finally:
            context.close()


# the studio module's fixture class must not be collected a second time from this module's namespace
del _Base
