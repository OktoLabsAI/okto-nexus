# TR4-14-05 Windows owner-crash containment

Two normative cases kill an explicitly owned laboratory supervisor before and
after durable process-birth recording. The supervisor imports the installed Core
under Python -I and uses its real Windows Job Object backend to spawn a harmless
Python process that creates a grandchild. The test opens stable OS handles for
all reported tree members before killing the supervisor. Every member is observed
stopped through those handles; a separate test-owned negative-control process
remains alive. Cleanup targets only the retained handles and test-created Popen
objects.

Before the crash, Core birth evidence reports MATCHING_LIVE. A modified birth
token reports DIFFERENT_BIRTH. A foreign-platform record reports UNKNOWN without
granting control of the separate process. After the crash, the recorded birth is
not live. The real journal retains SUBMISSION_STARTED, possible_effect=true and
the original claim generations. Missing birth evidence stays absent, and exact
replay returns the original receipt without fresh admission.

## Verification

The installed runner compares all Nexus, Connector and Core source/wheel/installed
package bytes, then executes test_ns14_05's two cases. Both passed on Windows.
The owner subprocess also asserts that Core was imported from site-packages.
Hardware platform, containment backend, tree member count, stop observation time
and retained receipt facts are recorded as JUnit properties. The initial two-case
run overlaps the final two-case run and is not counted twice.

No product code, containment requirement or readiness flag changed. The existing
capacity-metrics artifact tuple remains current.

## Scope

TR4-14-05 passes for Windows Job Objects at the OS-backend layer. This is a real
process crash, not a native-provider test or a remote-host campaign. Linux is not
qualified by this run; the test skips explicitly outside Windows. NS14.05 remains
partial pending its additional required legacy scenarios and platform acceptance.
Receipt uncertainty is retained even when OS process termination is observed.
The complete delivery objective and G0–G3 remain open.
