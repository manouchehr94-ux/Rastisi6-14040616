# Public-site photo assets

These nine WebP images were extracted without alteration from the `RastiSi_Public_Website_v2.html` visual reference supplied for the RastiSi public-site redesign.

They are used only in the marketing website (homepage, design playground, features and about page), not in real customer storefronts. Store names and products shown in the marketing mockups are illustrative, not customer testimonials, customer inventory or claims of actual merchant relationships.

Before a production launch, the site owner should confirm publication and commercial-use rights for the original reference images, or replace them with independently licensed or owned product photography.

Keep replacement photos in this folder, preserve descriptive alt text in templates, and prefer optimized, dimensioned WebP assets rather than remote hotlinks.

## Owner-managed replacements

The Platform Admin's **تصاویر سایت عمومی** page stores image overrides in the `PublicSitePhoto` database table and under `MEDIA_ROOT/portal/public-photos/`. Deploy `apps.portal` migration `0010` before using the new editor. Configure persistent `DJANGO_MEDIA_ROOT` and ensure public `MEDIA_URL` is served on the marketing host in production. Git pulls synchronize the code and nine bundled fallback WebPs, **not** uploaded photos or database content. Back up the media directory and database separately.

The tariff page is also backed by the Platform Admin's published Plan/PlanVersion records, not by this image directory.
