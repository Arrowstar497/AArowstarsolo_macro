import pydirectinput
import pyautogui
import time
import keyboard  # press "p" to stop

# ---------------- SETTINGS ----------------
CARDS_ENABLED = True
TOL_CARD = 12
CONFIRM_TIMEOUT = 1.5

# Timing
START_DELAY = 6            # wait after Startup() so you can earn money
POPUP_DELAY = 0.5          # let the game process the placement before clearing the popup
POST_PLACE_WAIT = 0.5        # wait after each successful placement
RESET_WAIT = 2             # pause when the mapping wraps back to the base spot

# Mapping
BASE_SPOT = (1275, 814)
STEP = 100                 # radius grows by this much
TRIES_PER_RADIUS = 3       # failed tries before the radius grows
MAX_RADIUS = 500           # past this, reset to the base spot
MAX_SPOT_X = 1600          # never click on the unit panel / F button

# No-go zones: rectangles (x1, y1, x2, y2) that placement clicks must never land in.
# The first one covers the yellow "F" toggle button on the panel's left edge
# (arrow measured at about x 1545-1620, y 757-854) plus a margin around it.
NO_GO_ZONES = [
    (1480, 690, 1660, 920),
]

# Popup / unit panel on the left that covers the cards. Clicking here closes it.
POPUP_CLICK = (200, 300)

# Cards: sampled inside the card body so weather doesn't change the colour
CARD_POINTS = [(786, 999), (1281, 999), (1775, 997)]
VISIBLE_CARD_POINTS = CARD_POINTS[:2]      # not covered by the panel
GREEN_CARD = (9, 54, 27)
RED_CARD = (56, 18, 18)
CARD_CLICK_Y = 699
CARD_CONFIRM = (1082, 1295)

# Upgrade slots in the F panel (slot 1 = newest unit).
# y values sit in the middle of each button's fill, so every state
# (bright, dull, yellow, blue, Max) reads cleanly instead of hitting the outline.
SLOTS = [(2010, 284), (2415, 284), (1992, 566), (2410, 566), (1994, 847),
         (2411, 847), (1996, 1129), (2411, 1129), (1994, 1411), (2411, 1411)]

# Slot colours
SLOT_MAXED = (80, 85, 90)     # fully upgraded (grey)
TOL_MAXED = 15
SLOT_BLUE = (0, 250, 255)     # unit 3's upgrade button (affordable)
TOL_BLUE = 40
OCCUPIED_SPREAD = 60          # any coloured button (green, dull green, yellow, blue...) = a unit is there
AFFORD_MIN_BRIGHT = 150       # bright + saturated = can afford the upgrade (green, yellow, ...)
AFFORD_MIN_SPREAD = 100       # dull buttons (e.g. 28,93,6) are below this and just wait
UNKNOWN_TIMEOUT = 10          # seconds an unreadable slot may block the queue before it is skipped

# Upgrades
UPGRADE_DELAY = 0.3           # pause between upgrade clicks
UPGRADE_IDLE = 0.5            # pause when nothing in the current tier is affordable
# Strict order: each tier must be fully maxed before the next starts.
# Units inside a tier rotate evenly.
UPGRADE_TIERS = [[1, 5], [2], [3], [4], [6]]

# Special-ability unit (hotbar key 3)
ABILITY_UNIT = 3
ABILITY_OFFSET = (-200, 60)   # from the slot's pixel to the unit's portrait (opens its panel)
ABILITY_BUTTON = (908, 660)   # ability button inside the unit's panel
ABILITY_OPEN_WAIT = 0.6       # time for the unit panel to open
ABILITY_REPEAT = 0            # seconds between re-uses; 0 = use once per unit

# How many of each unit to place, per phase
PHASE1 = {1: 2, 2: 4, 3: 1, 4: 1, 5: 1, 6: 1}   # 10 units
PHASE2 = {3: 2, 4: 3, 6: 2}                       # 7 more units

# ---------------- END SCREEN / REPLAY LOOP SETTINGS ----------------
END_CHECK_INTERVAL = 1.0      # seconds between end-screen checks (keeps the script fast)

# Victory / Defeat screen: detected by the green "Next" button + the dark dialog behind it.
# Both screens use the same button position and colour.
END_NEXT_CLICK = (1024, 1103)                 # centre of the Next button
END_NEXT_PIXELS = [(900, 1103), (1100, 1103)] # green fill either side of the "Next" text
NEXT_GREEN = (60, 218, 0)
TOL_NEXT = 30
END_DIALOG_PIXEL = (600, 1200)                # dark dialog background
DIALOG_BG = (21, 21, 21)
TOL_DIALOG = 15

NEXT_CLICKS = 5               # how many times to click Next
NEXT_CLICK_GAP = 1            # seconds between Next clicks

# Replay button (appears after the Next clicks)
REPLAY_CLICK = (1516, 319)
REPLAY_PIXELS = [(1400, 300), (1520, 290)]    # yellow fill of the button
REPLAY_YELLOW = (255, 215, 0)
TOL_REPLAY = 35
REPLAY_WAIT_TIMEOUT = 15      # seconds to wait for the Replay button before clicking anyway
REPLAY_LOAD_WAIT = 20         # seconds to let the new game load before the script restarts

PLACED_ORDER = []             # unit keys in the order they were placed
TAKEN = []                    # map spots that already have a unit
ability_ready = set()         # placement indices of ability units upgraded at least once
ability_last = {}             # placement index -> time the ability was last used

panel_open = False
watching_for_end = False      # True while a run is active (end screen checks are on)
last_end_check = 0


class GameEnded(Exception):
    """Raised when the Victory / Defeat screen is detected."""
    pass


# ---------------- HELPERS ----------------
def stop_check():
    global last_end_check
    if keyboard.is_pressed("p"):
        print("⛔ Stopped by user.")
        raise SystemExit

    # Rate-limited end screen check. stop_check() runs inside every loop,
    # so this catches the Victory / Defeat screen no matter what the script is doing.
    if watching_for_end and time.time() - last_end_check >= END_CHECK_INTERVAL:
        last_end_check = time.time()
        if EndScreenDetected():
            raise GameEnded

def SafeSleep(seconds):
    """Sleep in small chunks so 'p' still stops the script."""
    end = time.time() + seconds
    while time.time() < end:
        stop_check()
        time.sleep(0.1)

def close_to(pixel, target, tol):
    return all(abs(a - b) <= tol for a, b in zip(pixel[:3], target))

def spread(px):
    return max(px[:3]) - min(px[:3])

def is_card_colour(px):
    return close_to(px, GREEN_CARD, TOL_CARD) or close_to(px, RED_CARD, TOL_CARD)

def is_occupied(px):
    return spread(px) >= OCCUPIED_SPREAD

def is_affordable(px):
    if close_to(px, SLOT_BLUE, TOL_BLUE):
        return True
    return max(px[:3]) >= AFFORD_MIN_BRIGHT and spread(px) >= AFFORD_MIN_SPREAD

def is_maxed(px):
    return close_to(px, SLOT_MAXED, TOL_MAXED)

def slot_state(px):
    """maxed / afford (clickable) / dull (coloured but can't afford yet) / unknown."""
    if is_maxed(px):
        return "maxed"
    if is_affordable(px):
        return "afford"
    if is_occupied(px):
        return "dull"
    return "unknown"

def TogglePanel():
    global panel_open
    stop_check()
    pydirectinput.press("f")
    panel_open = not panel_open
    time.sleep(0.5)

def HoldI(seconds=3):
    stop_check()
    pydirectinput.keyDown("i")
    time.sleep(seconds)
    pydirectinput.keyUp("i")

def MoveDown(pixels=10000):
    stop_check()
    pydirectinput.moveRel(0, pixels, duration=0.5, relative=True)

def HoldO(seconds=3):
    stop_check()
    pydirectinput.keyDown("o")
    time.sleep(seconds)
    pydirectinput.keyUp("o")

def Startup():
    time.sleep(1)

    stop_check()
    pydirectinput.moveTo(60, 1565, duration=0.5)
    pydirectinput.click()

    stop_check()
    pydirectinput.moveTo(1616, 932, duration=0.5)
    pydirectinput.click()

    stop_check()
    pydirectinput.moveTo(1785, 331, duration=0.5)
    pydirectinput.click()

    stop_check()
    pydirectinput.moveTo(1110, 260, duration=0.5)
    pydirectinput.click()

# ---------------- END SCREEN ----------------
def EndScreenDetected():
    """Victory and Defeat share the same green Next button and dark dialog.
    All three samples must match, so gameplay colours can't trigger it by accident."""
    shot = pyautogui.screenshot()
    if not all(close_to(shot.getpixel(p), NEXT_GREEN, TOL_NEXT) for p in END_NEXT_PIXELS):
        return False
    return close_to(shot.getpixel(END_DIALOG_PIXEL), DIALOG_BG, TOL_DIALOG)

def ReplayDetected():
    shot = pyautogui.screenshot()
    return all(close_to(shot.getpixel(p), REPLAY_YELLOW, TOL_REPLAY) for p in REPLAY_PIXELS)

def HandleEndScreen():
    """Click Next NEXT_CLICKS times (1s apart), click Replay, then wait for the new game to load."""
    global watching_for_end
    watching_for_end = False                # don't re-trigger while we're clicking through
    print("🏁 Game over screen detected (Victory / Defeat)")

    for i in range(NEXT_CLICKS):
        stop_check()
        pydirectinput.moveTo(*END_NEXT_CLICK, duration=0.3)
        pydirectinput.click()
        print(f"   Clicked Next ({i + 1}/{NEXT_CLICKS})")
        SafeSleep(NEXT_CLICK_GAP)

    # wait for the Replay button to show up
    end = time.time() + REPLAY_WAIT_TIMEOUT
    found = False
    while time.time() < end:
        stop_check()
        if ReplayDetected():
            found = True
            break
        time.sleep(0.3)
    if not found:
        print("⚠ Replay button not detected, clicking its position anyway")

    stop_check()
    pydirectinput.press("f")                # close the unit manager once
    print("   Pressed F to close the unit manager")
    time.sleep(0.5)                         # let the panel finish closing

    stop_check()
    pydirectinput.moveTo(*REPLAY_CLICK, duration=0.3)
    pydirectinput.click()
    print("🔁 Clicked Replay")

    SafeSleep(REPLAY_LOAD_WAIT)             # let the new game load

# ---------------- CARDS ----------------
def CardsDetected():
    """Cheap check using only the two pixels the panel doesn't cover."""
    if not CARDS_ENABLED:
        return False
    shot = pyautogui.screenshot()
    return all(is_card_colour(shot.getpixel(p)) for p in VISIBLE_CARD_POINTS)

def HandleCards():
    if not CardsDetected():
        return False

    print("🃏 Card event detected")
    was_open = panel_open
    if panel_open:
        TogglePanel()                       # close panel so card 3 is visible

    time.sleep(0.3)                         # let the cards settle
    shot = pyautogui.screenshot()
    pixels = [shot.getpixel(p) for p in CARD_POINTS]
    print("   Card pixels:", pixels)

    choice = None
    for p, px in zip(CARD_POINTS, pixels):  # green first
        if close_to(px, GREEN_CARD, TOL_CARD):
            choice = p
            break
    if choice is None:
        for p, px in zip(CARD_POINTS, pixels):
            if close_to(px, RED_CARD, TOL_CARD):
                choice = p
                break

    if choice is not None:
        print(f"   Picking card at x={choice[0]}")
        stop_check()
        pydirectinput.moveTo(choice[0], CARD_CLICK_Y, duration=0.3)
        pydirectinput.click()
        time.sleep(0.3)
        pydirectinput.moveTo(*CARD_CONFIRM, duration=0.3)
        pydirectinput.click()
        time.sleep(0.5)

    if was_open and not panel_open:
        TogglePanel()                       # reopen panel only if we closed it
    return True

def WaitWithCards(seconds):
    """Wait, but keep watching for cards the whole time."""
    end = time.time() + seconds
    while time.time() < end:
        stop_check()
        HandleCards()
        time.sleep(0.3)

def ClearPopup():
    """Click the top-left area to close the placement popup / unit panel."""
    stop_check()
    pydirectinput.moveTo(*POPUP_CLICK, duration=0.3)
    pydirectinput.click()

# ---------------- MAPPING ----------------
def in_no_go(spot):
    x, y = spot
    return any(x1 <= x <= x2 and y1 <= y <= y2 for x1, y1, x2, y2 in NO_GO_ZONES)

def is_allowed(spot):
    """A spot is usable if it's left of the unit panel and outside every no-go zone."""
    return spot[0] <= MAX_SPOT_X and not in_no_go(spot)

def RingSpots(radius):
    """Spots exactly `radius` pixels out from the base (square ring), nearest first."""
    if radius == 0:
        offsets = [(0, 0)]
    else:
        offsets = [(dx, dy)
                   for dx in range(-radius, radius + 1, STEP)
                   for dy in range(-radius, radius + 1, STEP)
                   if max(abs(dx), abs(dy)) == radius]
    offsets.sort(key=lambda o: o[0] ** 2 + o[1] ** 2)
    return [(BASE_SPOT[0] + dx, BASE_SPOT[1] + dy) for dx, dy in offsets]

def NextSpot(radius, tries, taken):
    ring = [s for s in RingSpots(radius) if s not in taken and is_allowed(s)]
    if not ring:
        return None
    return ring[tries % len(ring)]          # small rings get retried

def PrintSpotReport():
    """Startup summary so you can see which spots the no-go rules removed."""
    all_spots = [s for r in range(0, MAX_RADIUS + 1, STEP) for s in RingSpots(r)]
    blocked = [s for s in all_spots if not is_allowed(s)]
    print(f"🗺 {len(all_spots) - len(blocked)} usable spots, {len(blocked)} blocked "
          f"(panel edge / no-go zones)")
    print("   Blocked inside the no-go zones:", [s for s in blocked if in_no_go(s)])

# ---------------- PLACEMENT ----------------
def slot_is_occupied(i):
    x, y = SLOTS[i]
    pixel = pyautogui.screenshot(region=(x, y, 1, 1)).getpixel((0, 0))
    return is_occupied(pixel)

def CountPlaced():
    """Coloured slots counted from the top. Older, fully upgraded units are grey,
    so in phase 2 this only counts the newly placed units."""
    shot = pyautogui.screenshot()
    n = 0
    for x, y in SLOTS:
        if is_occupied(shot.getpixel((x, y))):
            n += 1
        else:
            break
    return n

def TryPlace(unit, spot, placed):
    stop_check()
    pydirectinput.press(str(unit))
    time.sleep(0.15)
    pydirectinput.moveTo(*spot, duration=0.3)
    pydirectinput.click()

    end = time.time() + CONFIRM_TIMEOUT
    while time.time() < end:
        stop_check()
        if slot_is_occupied(placed):        # slot index `placed` = the next slot down
            return True
        time.sleep(0.1)
    return False

def WatchForever():
    print("👀 Now watching for cards and the end screen. Press 'p' to stop.")
    while True:
        stop_check()                        # also checks for the Victory / Defeat screen
        HandleCards()
        AbilityTick()
        time.sleep(0.5)

def PlaceUnits(counts):
    remaining = dict(counts)
    target = sum(counts.values())

    if not panel_open:
        TogglePanel()                       # open panel once

    radius = 0
    tries = 0

    while True:
        stop_check()
        HandleCards()

        placed = CountPlaced()
        if placed >= target:
            print(f"✅ Placed {target} units this phase.")
            return

        pending = [u for u in sorted(remaining) if remaining[u] > 0]
        if not pending:
            print("✅ No units left to place.")
            return
        unit = pending[0]                   # strict priority by key

        spot = NextSpot(radius, tries, TAKEN)
        if spot is None:                    # ring fully used or off-limits
            radius += STEP
            tries = 0
            if radius > MAX_RADIUS:
                print("↺ Mapping limit reached, back to base spot")
                radius = 0
                SafeSleep(RESET_WAIT)
            continue

        if TryPlace(unit, spot, placed):
            remaining[unit] -= 1
            PLACED_ORDER.append(unit)
            TAKEN.append(spot)
            radius = 0
            tries = 0
            print(f"✔ Placed unit {unit} at {spot} ({placed + 1}/{target})")
            SafeSleep(POPUP_DELAY)
            ClearPopup()
            WaitWithCards(POST_PLACE_WAIT)
        else:
            tries += 1
            print(f"✖ Unit {unit} failed at {spot} (try {tries}/{TRIES_PER_RADIUS}, radius {radius})")
            if tries >= TRIES_PER_RADIUS:
                radius += STEP
                tries = 0
                if radius > MAX_RADIUS:
                    print("↺ Mapping limit reached, back to base spot")
                    radius = 0
                    SafeSleep(RESET_WAIT)

# ---------------- ABILITY ----------------
def UseAbility(idx):
    """Open the unit's panel (click its portrait), press the ability, close the panel."""
    if not panel_open:
        TogglePanel()
    x, y = SLOTS[idx]
    print(f"✨ Using ability from slot {idx + 1}")

    stop_check()
    pydirectinput.moveTo(x + ABILITY_OFFSET[0], y + ABILITY_OFFSET[1], duration=0.2)
    pydirectinput.click()
    SafeSleep(ABILITY_OPEN_WAIT)

    pydirectinput.moveTo(*ABILITY_BUTTON, duration=0.2)
    pydirectinput.click()
    SafeSleep(0.3)

    ClearPopup()                            # close the unit panel
    SafeSleep(0.3)

def AbilityTick():
    """Re-use abilities on a timer (only when ABILITY_REPEAT > 0)."""
    if ABILITY_REPEAT <= 0:
        return
    total = len(PLACED_ORDER)
    now = time.time()
    for k in sorted(ability_ready):
        idx = total - 1 - k                 # where this unit sits in the panel now
        if idx >= len(SLOTS):
            continue                        # scrolled out of view
        if now - ability_last.get(k, 0) >= ABILITY_REPEAT:
            UseAbility(idx)
            ability_last[k] = time.time()

# ---------------- UPGRADES ----------------
def VisibleUnits(first_k=0):
    """(placement index, unit key, slot index) for units from first_k on that are
    inside the 10 visible slots. The newest unit is always slot index 0."""
    total = len(PLACED_ORDER)
    out = []
    for k in range(first_k, total):
        idx = total - 1 - k
        if idx < len(SLOTS):
            out.append((k, PLACED_ORDER[k], idx))
    return out

def ClickSlot(i):
    stop_check()
    x, y = SLOTS[i]
    pydirectinput.moveTo(x, y, duration=0.1)
    pydirectinput.click()

def UpgradeUnits(first_k=0):
    units = VisibleUnits(first_k)
    tiers = [[(k, idx) for k, unit, idx in units if unit in tier] for tier in UPGRADE_TIERS]
    print("🔧 Upgrade tiers (slot numbers):",
          [[idx + 1 for _, idx in t] for t in tiers])

    announced = set()
    warned = set()
    unknown_since = {}
    last_debug = 0
    while True:
        stop_check()
        HandleCards()
        if not panel_open:
            TogglePanel()
        AbilityTick()

        shot = pyautogui.screenshot()
        px = {idx: shot.getpixel(SLOTS[idx]) for t in tiers for _, idx in t}
        states = {idx: slot_state(p) for idx, p in px.items()}
        now = time.time()

        # If every slot is unreadable the panel is probably closed, so don't skip anything.
        all_unknown = bool(states) and all(s == "unknown" for s in states.values())
        skipped = set()
        for idx, st in states.items():
            if st == "maxed" and idx not in announced:
                announced.add(idx)
                print(f"⬆ Slot {idx + 1} fully upgraded")
            if st == "unknown" and not all_unknown:
                unknown_since.setdefault(idx, now)
                if now - unknown_since[idx] >= UNKNOWN_TIMEOUT:
                    skipped.add(idx)        # unreadable too long: stop it blocking the queue
                    if idx not in warned:
                        warned.add(idx)
                        print(f"⚠ Slot {idx + 1} unreadable {px[idx]} for {UNKNOWN_TIMEOUT}s, skipping it")
            else:
                unknown_since.pop(idx, None)

        # first tier that still has units to upgrade (strict order)
        active = None
        for t in tiers:
            left = [(k, idx) for k, idx in t if states[idx] != "maxed" and idx not in skipped]
            if left:
                active = left
                break

        if active is None:
            print("🏁 All units in this phase fully upgraded.")
            return

        affordable = [(k, idx) for k, idx in active if states[idx] == "afford"]
        if not affordable:
            if time.time() - last_debug > 5:
                last_debug = time.time()
                print("⏳ Waiting on slots:", {idx + 1: (px[idx], states[idx]) for _, idx in active})
                if all_unknown:
                    print("   Every slot is unreadable. Is the F panel open?")
            SafeSleep(UPGRADE_IDLE)         # nothing affordable yet, wait for money
            continue

        for k, idx in affordable:           # one click each = even rotation
            ClickSlot(idx)
            SafeSleep(UPGRADE_DELAY)
            if PLACED_ORDER[k] == ABILITY_UNIT:
                ability_ready.add(k)        # upgraded once, ability is now available
                if k not in ability_last:
                    UseAbility(idx)
                    ability_last[k] = time.time()

# ---------------- ONE FULL GAME ----------------
def ResetState():
    """Wipe everything the script remembers about the previous game."""
    global panel_open, last_end_check
    PLACED_ORDER.clear()
    TAKEN.clear()
    ability_ready.clear()
    ability_last.clear()
    panel_open = False                      # new game starts with the F panel closed
    last_end_check = 0

def RunGame():
    """The original start-to-finish script. Only returns by raising GameEnded
    (or SystemExit when you press 'p'), because it ends in WatchForever()."""
    time.sleep(3)
    HoldI()
    MoveDown()
    HoldO()
    Startup()
    SafeSleep(START_DELAY)                  # time to earn money before placing

    # Phase 1: place the first 10 units and upgrade them all
    PlaceUnits(PHASE1)
    UpgradeUnits(first_k=0)

    # Phase 2: extra units take the top slots, so the same slot positions are reused
    print("▶ Phase 2: placing additional units")
    phase2_start = len(PLACED_ORDER)
    PlaceUnits(PHASE2)
    UpgradeUnits(first_k=phase2_start)

    WatchForever()

# ---------------- MAIN ----------------
if __name__ == "__main__":
    PrintSpotReport()
    run = 1
    while True:                             # infinite loop, stop with 'p'
        print(f"\n===== 🔁 RUN #{run} =====")
        ResetState()
        watching_for_end = True             # turn end-screen detection on for this run
        try:
            RunGame()
        except GameEnded:
            pass
        HandleEndScreen()                   # Next x5 -> Replay -> wait for load
        run += 1