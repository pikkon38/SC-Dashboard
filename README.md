# Star Citizen Dashboard

A touch dashboard for your iPad (or any tablet or phone) that controls Star Citizen on your Windows PC. Power distribution (pips) is the main screen. Flight, Combat, Mining and Salvage each have their own screen, and every screen except Setup has Accept, Decline, Chat, head tracking and Exit Seat in the side key columns of its frame.

## Install

1. Download **SC-Dashboard-x.y.z-Setup.exe** from the [latest release](https://github.com/pikkon38/sc-dashboard/releases/latest) and run it.
   It isn't code-signed, so Windows may say "Windows protected your PC": click **More info**, then **Run anyway**.
2. SC Dashboard starts in the system tray (click the **^** by the clock if you don't see it). The first time, Windows Firewall asks about SC Dashboard. Allow it on **Private networks**.
3. Click the tray icon to copy the iPad address (like `http://192.168.1.20:8770`), and open it in Safari on the iPad (same Wi-Fi). Use Share > Add to Home Screen for full screen.
4. Click into Star Citizen so it's the focused window. The dot in the top right turns green when the game is focused.

## Updates

The tray app checks for a new release when it starts and every few hours. With **Install updates when it starts** ticked (the default) it updates itself at startup; otherwise right-click the tray icon and choose **Update**. The iPad page reloads on its own once the new version is running.
Your keybinds and ship data are kept in `%APPDATA%\SC Dashboard`, so updates and reinstalls never touch them. The first run brings over keybinds from an old unzipped copy on your Desktop, Downloads or Documents.

### Running from source

Install Python 3, then double-click **Start SC Dashboard.bat** (runs the companion in a console window, no tray). Close the tray app first, since both use port 8770.

### Publishing a release

Bump the number in `VERSION`, write the notes in `CHANGES.md`, and push to main. GitHub Actions builds and tests the installer on Windows and publishes it as release v<VERSION>.

## Screens

- **Power**: tap or drag a pip stack, or use the − and + buttons under it (hold for min/max). On phones held sideways the stacks give way to big − and + buttons; Setup › Ship & pips › Power controls can make that the default everywhere. **FLT READY** on the Power screen powers the ship up, waits for it to boot, then sets the pips to what the dashboard shows (like SYNC).
- **Flight**: decoupled, cruise, G-safe, ESP, speed limiter and pitch/yaw lock switches with speed limit steps and throttle min/max; a landing gear lever, VTOL, request landing and autoland (hold); exterior lights, night vision (LAMP), look behind and freelook (held until you tap again); docking, port lock and cargo loading; Starmap and mobiGlas; and small cabin buttons (doors, locks, wipe visor, 3rd person). The red emergency keys along the bottom are Emergency exit, Eject and Self destruct (all hold).
- **Self destruct**: once it's armed the whole screen pulses red on every tab, with a Hold to cancel button. The game doesn't report self destruct, so the dashboard tracks its own press: the alarm stops when you cancel, leave the seat, die, or after 3 minutes. Self destruct started from your stick doesn't show.
- **Combat**: decoys with burst size, noise and panic launch; a targeting wheel (hostiles, attackers, friendlies, all, ahead), lock and pin slots, sub-targets, auto targeting and look ahead; weapon presets, gimbal lock, precision targeting, staggered fire and aim mode; and missile arming.
- **Mining**: a laser power slider, a Fire button, laser switch, high/low power, consumable modules 1 to 3, and jettison cargo (hold).
- **Salvage**: left and right heads, beam spacing slider, head focus, Scrape button, fracture and disintegrate heads.
- Buttons marked "hold" need a press of about a second so they can't fire by accident.
- **Fire / Scrape** hold the left mouse button down until you tap again. Switching away from the dashboard app releases it.
- **Sliders** send mouse wheel notches, the same as scrolling in game. The game doesn't report the real value, so if they drift, tap **Re-zero** to bottom it out and start again.
- **Accept / Decline** have no default key in Star Citizen. Bind them in game, then enter the same keys in Setup.

## Sounds

Each kind of control has its own sound: power pips charge up and down (higher pitch the fuller the system), lasers spool up and discharge, the gear lever runs a hydraulic motor, quantum spools, Accept and Decline chime, and so on.
In **Setup › Feedback › Play sounds on** choose This iPad, PC speakers, Both or Off. PC sounds play through your default Windows output and follow the dashboard volume.
The sounds are WAV files in companion/web/sounds. To change them, edit make_sounds.py and run `py -3 make_sounds.py`.

## Ship detection

The PC app watches Star Citizen's `Game.log` (it looks in the usual install folders; otherwise start it with `--log "X:\path\to\StarCitizen\LIVE\Game.log"`).
When you board a ship, the game logs that you joined the ship's channel. The dashboard then shows the ship's name, colors the screen by manufacturer (Setup > Screen color > Auto), and loads pip counts from the community Star Citizen wiki when it has them (many ships don't have this data yet). When you leave the ship it shows NO SHIP.
Pip edits you make in Setup are remembered per ship.

## Keybinds from your game

The PC app also reads your game keybinds (`user\client\0\Profiles\default\actionmaps.xml`) and uses any **keyboard** binds you've set there for toggles like G-safe, ESP, VTOL, lights and doors. These show as "from your game settings" in Setup.
The dashboard can only send keyboard keys, not joystick buttons. If an action is only bound to your joystick, add a keyboard bind for it in game as well (Star Citizen keeps both).

## Keybinds

Defaults match Star Citizen 4.x: F5/F6/F7 raise weapons/thrusters/shields, Left Alt + F5/F6/F7 lower them, holding sets max/min, F8 resets, U/P/O/I toggle power.
G-safe, ESP, speed limiter and doors have **no default key in game**. Bind them in Star Citizen first (Options > Keybindings), then enter the same key in the dashboard's **Setup** tab and tap Save.
Binds are stored in `companion/keybinds.json` on the PC.

## Pips and staying in sync

Star Citizen doesn't send its power state to outside apps, so the dashboard keeps its own copy of the pips. It stays correct as long as power is changed from the dashboard.
If you change power in game (or switch ships), tap **Reset** on the dashboard (sends F8), or turn on **Sync** and tap the pips to match the game without sending keys.
Pip counts differ by ship: set them in **Setup > Ship pips**.

## Options

- `Start SC Dashboard.bat --pin 1234` requires a PIN (enter it in Setup > Connection).
- `--dry-run` logs presses without sending keys, for testing.
- `--port 8770` changes the port.

## Troubleshooting

- **Keys do nothing in game:** the game must be the focused window. If you run Star Citizen as administrator, run the .bat as administrator too (Windows blocks input from a lower-privilege app).
- **iPad can't load the page:** check both are on the same network and the firewall prompt was allowed.
