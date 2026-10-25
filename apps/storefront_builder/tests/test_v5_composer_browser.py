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
        page.click('[data-rs-composer="add-row"]')
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
        page.wait_for_selector('[data-cmp-panel]:not([hidden]) [data-cmp-text="title"]', timeout=8000)

    def open_section(self, page, title):
        summary = page.locator("[data-cmp-panel] details.rs-cmp-sect > summary", has_text=title).first
        if not summary.evaluate("s => s.parentElement.open"):
            summary.click()

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
            page.select_option("[data-cmp-bg-mode]", "gradient")
            page.wait_for_timeout(900)
            page.locator('[data-cmp-theme="3"]').click()                    # «برند»: gradient + brand text colours in one click
            page.wait_for_timeout(900)
            page.select_option('[data-cmp-choice="style:text_align"]', "center")
            self.open_section(page, "فاصله‌ها")
            page.locator('[data-cmp-int-num="style:pad"]').fill("28")
            self.open_section(page, "حاشیه")
            page.locator('[data-cmp-int-num="style:radius"]').fill("26")
            self._until(page, f"""()=>{{const c=document.querySelector('.rcontainer[data-container-id="{parent}"]'); const g=c&&c.closest('.rgroup');
              return g && g.querySelector('.rgroup-title') && g.querySelector('.rgroup-title').textContent.trim()==='مجموعهٔ پاییزی' && getComputedStyle(g).paddingTop==='28px'
                && getComputedStyle(g).borderTopLeftRadius==='26px' && getComputedStyle(g).backgroundImage.includes('linear-gradient')}}""", "the parent group look")
            view = self.group_view(page, parent)
            self.assertEqual((view["title"], view["desc"], view["align"]), ("مجموعهٔ پاییزی", "ویژه مشتریان وفادار", "center"))
            # the CHILDREN: the first cell becomes its own group with another look; the parent's look is untouched
            self.settle(page)
            page.click("[data-cmp-panel-close]")                            # the floating panel is closed so it does not cover the canvas
            self.pick_leaf(page, base)
            self.split(page, "vertical", 2)
            child = self.selected_group_id(page)
            self.assertNotEqual(child, parent)
            self.edit_group(page)
            self.type_into(page, '[data-cmp-text="title"]', "کودک اول")
            page.select_option("[data-cmp-bg-mode]", "color")
            page.wait_for_timeout(900)
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
