Beraito exact frontend V4

V4 fixes the remaining offline-capture lifecycle issues:
- all Beraito wp-content/upload image URLs used by the homepage are localized from the WebScrapBook capture
- primary product-card images no longer depend on the live site while hover images still work normally
- the large "پیشنهاد شگفت انگیز برایتو" widget is initialized directly (Owl Carousel) with a dependency-free fallback
- the top "پیشنهادات لحظه ای برایتو" and hero repairs from V3 are retained

Run:
  python -m http.server 8767 --bind 127.0.0.1
Open:
  http://127.0.0.1:8767/

V5 final correction:
- Removed 38 zero-byte image candidates from responsive srcset data in the homepage capture.
- Compacted only the four paired product panels to the live-site desktop proportions.
- Footer and already-approved bottom section are unchanged.
