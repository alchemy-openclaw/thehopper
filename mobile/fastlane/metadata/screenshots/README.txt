Place screenshot images here for each device size.

App Store requires screenshots for at least one iPhone size before you can
submit for review. Both release lanes currently pass skip_screenshots, so
fastlane will NOT upload these — add them in App Store Connect directly, or
remove that flag once these files exist.

Required screenshots (minimum 1, recommended 3-5), matching the current tabs:
1. Find    — venue list sorted by distance
2. Event   — live event screen with chat and lineup actions
3. My Songs — song browser with search and favorites
4. Event   — skip-the-line / tip payment modal
5. Add Spot — add a venue / KJ onboarding

File naming: 1_find.png, 2_event.png, 3_songs.png, 4_payment.png, 5_addspot.png

Capture manually from the simulator (Cmd+S in Simulator) — the `screenshots`
lane was removed because capture_screenshots needs a Snapfile and a UI test
target, neither of which exists in this project.
