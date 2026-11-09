# Preserved V2 development observations

- Initial serializer negative test: 23/24 passed. The installed serializer rejects
  disabled pickle with NotImplementedError; the assertion originally expected ValueError.
- Initial interrupt smoke: writing latency with graph.update_state removed the
  pending interrupt from the public view. Latency moved to registry metadata.
- Extended safety run: 39/41 passed. Category conflicts were retained as gaps but
  missed a severity-specific human-review edge; the edge now handles all context conflicts.
  Poisoned policy text was already rejected before selection, correctly returning
  insufficient evidence. The assertion now accepts either safe rejection path while
  still requiring no findings or recommendations.
- Fresh Dockerfile build failed twice while resolving the official Python base image
  with registry HTTP 503. A cached-runtime offline compatibility image was validated
  separately; it does not erase this fresh-build gap.
- First Linux pytest harness failed because the /tmp tmpfs hid its wheel directory.
  A read-only wheelhouse mount corrected the harness; the rerun passed 149 tests.
  Nine Git publication tests were excluded from the slim Linux runtime and passed
  in both complete macOS runs. This was a harness correction, not an application fix.
- The first reserved suite passed 12/12. Its results were not used for behavior tuning.
  Later UI text formatting changed presentation only; core graph/rules stayed fixed.
