# EF-2000 Typhoon for Nuclear Option

Turns the FS-12 Revoker into a Eurofighter Typhoon: a complete new exterior and a fully modelled, working cockpit. Flight performance, weapons and damage are the Revoker's own, unchanged.

**Download:** get both zips from the latest release on the [Releases](../../releases) page.

**AI disclosure:** this mod was developed with AI. The plugin code and the scripts that build the model and textures were written by Claude, Anthropic's AI model, directed and tested in game by Assassin.

## The model in numbers
- **401,938 triangles** in 166 separate parts
  - Cockpit: 248,288 triangles
  - Exterior: 153,650 triangles
- **Over 80 texture maps** (colour, normal and surface maps), up to **8192 x 8192** for the fuselage and wings, shipped pre-compressed so they load fast
- **26 moving parts** linked to the game's own controls and systems
- **7 working cockpit displays** and **89 lit legends** that follow the aircraft's state

## Exterior
- Canards, inboard and outboard flaperons, rudder and airbrake all move with the flight controls
- Engine nozzles: petals open and close with throttle and afterburner, and follow the game's thrust vectoring
- Its own afterburner flame on both nozzles, with heat haze behind the engines
- Landing gear: three legs that fold away behind their doors, with working suspension travel, spinning wheels, nose-wheel steering, a landing light on the nose leg and wheel chocks
- Internal weapon bay with opening doors and a rotary launcher
- Seven weapon stations placed for the Typhoon: cannon, two bay mounts, two wing pylons and two wingtip rails
- Wingtip navigation lamps (red and green) with a halo visible from a distance, and formation light strips
- Painted markings: roundels, serial, tail code and fin badge
- Its own engine sounds: turbine, dry thrust, afterburner, afterburner light-off and fly-bys

## Cockpit
- Fully modelled interior: front panel, both side consoles, pedestal, HUD frame, ejection seat, canopy arch and sills, footwells and the area behind the seat
- Seven live displays:
  - Left display: engine, fuel and hydraulics pages
  - Centre display: a Typhoon-style radar page, switching to the game's target camera and landing camera
  - Right display: flight page, moving map drawn from the game's terrain, and weapons page
  - Keypad display with waypoint read-out and in-game chat
  - Warning panel and standby attitude indicator
- Three standby gauges with moving needles: airspeed, climb rate and altitude
- 89 backlit key legends that light according to what the aircraft is doing (radar, weapons, navigation, engine, fuel and more)
- Soft keys press in when you change a display page
- Stick, throttle, rudder pedals and gear lever move with your inputs
- Console switches follow the real state of gear, ignition, navigation lights and radar
- Gear lamps: red while the legs travel, green when down and locked
- Night lighting: backlit legends, and displays that dim after dark
- The pilot sits in the Typhoon's seat, and the view is set to the Typhoon's eye point

## Performance
- Everything heavy is loaded once at game start, spread over many frames, so spawning a Typhoon causes no long pause
- Typhoons more than 90 m away draw a reduced interior (about 38,000 cockpit triangles instead of 248,000)

**Why 1.1 GB of video memory?** Almost all of it is textures. The cockpit is seen from arm's length, so its panels use up to 7.6 pixels per millimetre to keep every label readable, and the fuselage and wings use 8192 x 8192 maps so markings stay sharp in external view. All textures are stored compressed (a quarter of their raw size) and are shared between every Typhoon in the mission.

## Needs
- Nuclear Option (Steam, Windows) with BepInEx 5 (x64)
- About 1.4 GB of disk space

## Install
1. Close the game.
2. Download BOTH zips (part1 and part2) from the latest release and unzip both into the game folder (the one with NuclearOption.exe). They go to the same place: `BepInEx\plugins\TyphoonMod`
3. Start the game. The first start takes a little longer once, while some textures are prepared.

## Controls
- `[` steps the left display through its pages
- `]` steps the right display through its pages
- Everything else is the game's own controls

## Good to know
- There are no settings and no config file.
- Other players only see the Typhoon if they have the mod too; without it they see the Revoker.
- To update, unzip the new version over the old one. To remove, delete the `TyphoonMod` folder.
- If something looks wrong, open an issue with `BepInEx\LogOutput.log` and a screenshot.

## Source available
This repository holds the source of the plugin (`src`, C#) and the scripts that build the model and its textures (`model`, `dev/tools`). It is published so you can read it and see how the mod works.

**Please ask before changing or redistributing it.** The plugin, its source, the scripts and the data files are the author's own work: changing them, publishing changed versions or re-uploading them needs permission first. Open an issue and say what you want to do. See [LICENSE.txt](LICENSE.txt).

To build the plugin: copy `Directory.Build.props.example` to `Directory.Build.props`, set your game path in it, then run `dotnet build -c Release`. For the release build without settings add `-p:DefineConstants=PRODUCTION`. The model scripts need source files that are not in this repository (the original model and working inputs), so they are here to read, not to run as they are.

## Licence and credits
Free and non-commercial.
- **The plugin and its source:** source available, permission required. See [LICENSE.txt](LICENSE.txt).
- **Aircraft model:** ["Eurofighter Typhoon - Fighter Jet - Free" by bohmerang](https://sketchfab.com/3d-models/eurofighter-typhoon-fighter-jet-free-992bcc8987964ca09d55410330aa8579) (Sketchfab), CC BY-NC-SA 4.0, adapted and extended for this mod. The adapted model and its textures are shared under the same licence. See [CREDITS.txt](CREDITS.txt).

Not affiliated with Shockfront Studios or Eurofighter GmbH.
