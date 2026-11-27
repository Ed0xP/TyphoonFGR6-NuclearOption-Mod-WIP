using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using BepInEx;
using HarmonyLib;
using BepInEx.Configuration;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace TyphoonMod
{
    [BepInPlugin(Guid, Name, Version)]
    public class TyphoonPlugin : BaseUnityPlugin
    {
        static void Live<T>(BepInEx.Configuration.ConfigEntry<T> e, System.Action<T> set)
        {
            set(e.Value);
            e.SettingChanged += (s, a) => set(e.Value);
        }

        public const string Guid = "assassin.nuclearoption.typhoon";
        public const string Name = "Eurofighter Typhoon";
        public const string Version = "1.0.1";

        const BindingFlags AllInstance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

        ConfigEntry<bool> _enabled;
        ConfigEntry<string> _baseAircraft;
        ConfigEntry<bool> _rename;
        ConfigEntry<string> _displayName;
        ConfigEntry<string> _description;
        ModelSwap _swap;
        internal static TyphoonPlugin Instance;

        readonly HashSet<AircraftDefinition> _done = new HashSet<AircraftDefinition>();
        float _nextScan;

#if PRODUCTION
        internal static readonly bool Locked = true;
#else
        internal static readonly bool Locked = false;
#endif
        ConfigFile _settings;
        ConfigFile Settings
        {
            get
            {
                if (_settings != null) return _settings;
                if (!Locked) return _settings = Config;
                string nowhere = Path.Combine(Path.Combine(Paths.CachePath, "TyphoonMod"), "fixed-" + System.Guid.NewGuid().ToString("N") + ".none");
                _settings = new ConfigFile(nowhere, false);
                _settings.SaveOnConfigSet = false;
                return _settings;
            }
        }

        void BindTone(string key, float def, string help, params string[] materials)
        {
            var e = Settings.Bind("Cockpit", key, def, new BepInEx.Configuration.ConfigDescription(help, new BepInEx.Configuration.AcceptableValueRange<float>(0.4f, 2.5f)));
            foreach (var mname in materials) TexturedMaterials.Tone[mname] = e.Value;
            e.SettingChanged += (snd, arg) => { foreach (var mname in materials) TexturedMaterials.SetTone(mname, e.Value); };
        }

        void Awake()
        {
            _enabled = Settings.Bind("General", "Enabled", true, "Turn the Typhoon conversion on or off (restart the game after changing).");
            _baseAircraft = Settings.Bind("General", "BaseAircraft", "FS-12 Revoker",
                "In-game aircraft to convert into the Typhoon (its unitName or aircraftName).");

            _rename = Settings.Bind("Identity", "Rename", true, "Show the converted aircraft as the Typhoon in menus and the HUD.");
            _displayName = Settings.Bind("Identity", "DisplayName", "EF-2000 Typhoon", "Name shown in game.");
            _description = Settings.Bind("Identity", "Description",
                "Twin-engine, canard-delta multirole fighter. Two EJ200 turbofans (60 kN dry / 90 kN reheat each) " +
                "give a thrust-to-weight ratio above 1, supercruise near Mach 1.5 and a top speed of Mach 2. " +
                "Relaxed stability and a fly-by-wire system make it exceptionally agile.",
                "Encyclopedia text.");

            if (Locked) Logger.LogInfo("Production build: settings are fixed (no config file is read or written).");
            if (!_enabled.Value)
            {
                Logger.LogInfo("Typhoon mod disabled in config.");
                return;
            }

            Instance = this;
            _swap = new ModelSwap(Settings, Logger, Path.GetDirectoryName(typeof(TyphoonPlugin).Assembly.Location));
            try { var h = new Harmony(Guid); h.PatchAll(typeof(AircraftAwakePatch)); h.PatchAll(typeof(TurbojetAnimatePatch)); h.PatchAll(typeof(NozzleAudioPatch)); h.PatchAll(typeof(AfterburnerAudioPatch)); h.PatchAll(typeof(AfterburnerRunPatch)); ChatFeed.Install(h, Logger); }
            catch (Exception e) { Logger.LogWarning($"Spawn hook not installed (the original may flash briefly on spawn): {e.Message}"); }
            Live(Settings.Bind("Sound", "TurbineIdlePitch", 1.0f, "Playback speed of turbine.ogg at idle RPM (1 = as recorded)."), v => TyphoonSounds.IdlePitch = v);
            Live(Settings.Bind("Sound", "TurbineFullPitch", 1.6f, "Playback speed of turbine.ogg at full RPM."), v => TyphoonSounds.FullPitch = v);
            Live(Settings.Bind("Sound", "RoarVolume", 0.9f, "Loudness of thrust.ogg relative to the game's own level (capped at full volume)."), v => TyphoonSounds.RoarGain = v);
            Live(Settings.Bind("Sound", "AfterburnerVolume", 1.6f, "Loudness of afterburner.ogg relative to the game's own level."), v => TyphoonSounds.AfterburnerGain = v);
            Live(Settings.Bind("Sound", "RoarPitchWander", 0.03f, "Random slow pitch drift on the roar sounds (0.03 = +/-3%) so they don't sound like a loop. 0 = off."), v => TyphoonSounds.Wander = v);
            Live(Settings.Bind("Sound", "AfterburnerFadeIn", 1.2f, "Seconds for the afterburner roar to swell in when reheat lights."), v => TyphoonSounds.FadeIn = v);
            Live(Settings.Bind("Sound", "AfterburnerFadeOut", 0.9f, "Seconds for the afterburner roar to die away when reheat is cancelled."), v => TyphoonSounds.FadeOut = v);
            Live(Settings.Bind("Sound", "LightOffVolume", 0.9f, "Volume of the rumble when reheat lights (lightoff.ogg). 0 = off."), v => TyphoonSounds.LightOffVolume = v);
            Live(Settings.Bind("Sound", "TurbineVolume", 0.7f, "Overall volume of the engine whine (turbine.ogg)."), v => EngineSoundShaper.TurbineVolume = v);
            Live(Settings.Bind("Sound", "TurbineFrontVolume", 0.35f, "Whine volume when heard from in front of the jet, relative to behind it."), v => EngineSoundShaper.TurbineFrontVolume = v);
            Live(Settings.Bind("Sound", "MachConeSilence", true, "When supersonic, the engines can't be heard until the shock cone has passed you."), v => EngineSoundShaper.MachCone = v);
            Live(Settings.Bind("Sound", "FrontVolume", 0.6f, "Volume of the approaching-jet sound (front.ogg) heard from ahead of the jet."), v => EngineSoundShaper.FrontVolume = v);
            Live(Settings.Bind("Sound", "FlybySounds", true, "Play a recorded fly-by when the jet passes close to a stationary/slow camera."), v => EngineSoundShaper.Flyby = v);
            Live(Settings.Bind("Sound", "FlybyVolume", 1.0f, "Volume of the recorded fly-bys."), v => EngineSoundShaper.FlybyVolume = v);
            Live(Settings.Bind("Sound", "FlybyDistance", 150f, "How close (m) the jet must pass the camera to trigger a fly-by."), v => EngineSoundShaper.FlybyDistance = v);
            Live(Settings.Bind("Sound", "FlybyEngineDuck", 0.35f, "Engine loop volume while a fly-by plays (the recording already contains the engines)."), v => EngineSoundShaper.FlybyDuck = v);
            Live(Settings.Bind("Sound", "DistantRumbleVolume", 1.0f, "Volume of the long-range roar/crackle heard when the jet is far from the camera (0 = off)."), v => EngineSoundShaper.RumbleVolume = v);
            Live(Settings.Bind("Sound", "DistantRumbleStart", 120f, "Distance (m) where the distant rumble starts taking over from the close-up sounds."), v => EngineSoundShaper.RumbleStart = v);
            Live(Settings.Bind("Sound", "DistantRumbleFull", 600f, "Distance (m) where the close-up whine/whoosh is mostly gone and the rumble dominates."), v => EngineSoundShaper.RumbleFull = v);
            TyphoonEditor.Setup(gameObject, Settings, Path.GetDirectoryName(typeof(TyphoonPlugin).Assembly.Location), Logger, !Locked);
            Live(Settings.Bind("Sound", "SupersonicRumble", 1.0f, "Volume of the deep rumble layer after a supersonic pass (0 = off)."), v => EngineSoundShaper.BoomRumble = v);
            Live(Settings.Bind("Sound", "CloseWhineBoost", 1.6f, "Extra engine whine when the camera is right next to the jet, for a closer, brighter sound."), v => EngineSoundShaper.CloseWhineBoost = v);
            TyphoonVisual.AirbrakeAngle = Settings.Bind("Model", "AirbrakeAngle", 50f, "How far (degrees) the dorsal airbrake opens.").Value;
            TexturedMaterials.CacheDir = Path.Combine(Paths.CachePath, "TyphoonMod");
            TexturedMaterials.UsePacked = Settings.Bind("Model", "PackedTextures", true,
                "Use the ready-compressed textures shipped with the mod (<name>.tex, sharper and quicker to load). Off = load the PNG\n" +
                "files and let the game compress them, as before 1.9.1 (needs a restart).").Value;
            string toneHelp = " Higher = lighter, lower = darker (1 = the bare texture). Applied at once (no restart).";
            BindTone("FrontPanelTone", 1.414084f, "Brightness of the front instrument panel paint and its key caps." + toneHelp, "ckpanel");
            BindTone("DisplayHousingTone", 1.977465f, "Brightness of the dark housings round the three head-down displays and the standby gauges." + toneHelp, "ckunit", "ckunitedge");
            BindTone("ConsoleTone", 1.247887f, "Brightness of the side consoles, gear panel, warning-panel surround and pedestal panel." + toneHelp, "ckconr", "ckconl", "ckconsole", "ckgear", "ckdwp", "cknve");
            BindTone("FrameTone", 1.423944f, "Brightness of the canopy sills, windscreen arch, the metal parts on them, and the tub walls and footwell." + toneHelp, "ckframe", "ckfdeck", "ckfaft", "ckcanfr", "ckliner", "cktub", "ckrest", "ckrail", "ckmetaldark", "ckdeck", "ckwall", "ckplate");
            var sense = Settings.Bind("Cockpit", "StandbyNeedlesReversed", false,
                "Turn this on if the three standby gauge needles (right of the right display) turn the wrong way round. Applied at once.");
            TyphoonCockpit.NeedleSense = sense.Value ? -1f : 1f;
            sense.SettingChanged += (snd, arg) => { TyphoonCockpit.NeedleSense = sense.Value ? -1f : 1f; };
            var dispMargin = Settings.Bind("Cockpit", "DisplayMargin", 3f, new ConfigDescription(
                "Millimetres of black glass left round the picture of the three head-down displays and the warning panel, so that the bezel does not cut into the picture when a display is seen from the side. 0 = the picture fills the glass (as before 2.2.3). Takes effect the next time the aircraft is spawned.",
                new AcceptableValueRange<float>(0f, 10f)));
            TyphoonCockpit.DisplayMargin = dispMargin.Value / 1000f;
            dispMargin.SettingChanged += (snd, arg) => { TyphoonCockpit.DisplayMargin = dispMargin.Value / 1000f; };
            var radarZoom = Settings.Bind("Cockpit", "RadarZoom", 1.0f, new ConfigDescription(
                "Size of the part of the game's radar picture the centre display shows, centred on the scope: 1 = just inside the radar's own white frame; above about 1.05 the frame shows, below 1 the scope is enlarged. Takes effect the next time the aircraft is spawned. Ignored when TacScreenArea is set by hand. (Replaces RadarZoomOut of 2.2.5, which is no longer read.)",
                new AcceptableValueRange<float>(0.8f, 1.3f)));
            TyphoonCockpit.RadarZoom = radarZoom.Value;
            radarZoom.SettingChanged += (snd, arg) => { TyphoonCockpit.RadarZoom = radarZoom.Value; };
            var ownRadar = Settings.Bind("Cockpit", "TyphoonRadarPage", true,
                "The centre display shows the game's radar data as a Eurofighter-style radar page (B-scope, tracks coloured friendly / hostile / unknown with altitude and heading, the selected target circled). Off: the copy of the game's own radar picture. The target and landing cameras always show the game's picture. Takes effect at the next radar / camera switch or spawn.");
            TyphoonCockpit.OwnRadar = ownRadar.Value;
            ownRadar.SettingChanged += (snd, arg) => { TyphoonCockpit.OwnRadar = ownRadar.Value; };
            var keyAnim = Settings.Bind("Cockpit", "KeyPressAnimation", true,
                "The soft key of a display page ([ and ] keys) presses into its pocket when the page is called. Turn off if the keys ever look wrong. (The console switches RADAR, EXT LIGHT, BATT, L GEN, R GEN and FCS follow the game either way.)");
            TyphoonCockpit.KeyPressAnim = keyAnim.Value;
            keyAnim.SettingChanged += (snd, arg) => { TyphoonCockpit.KeyPressAnim = keyAnim.Value; };
            var texSharp = Settings.Bind("Cockpit", "TextureCrispness", 0.3f,
                "How much sharper than the game's own choice the cockpit's textures, lettering and displays are sampled when they are small on screen (0 - 1; 0 = the game's choice: smooth but soft, " +
                "higher = crisper but grainy, and it can shimmer when the view moves). Takes effect at the next start of the game.");
            TexturedMaterials.CockpitSharpness = Mathf.Clamp(texSharp.Value, 0f, 1f);
            var aniso = Settings.Bind("Cockpit", "AnisotropicFiltering", true,
                "The cockpit's textures ask for anisotropic filtering (sharp at flat angles: the consoles, the glareshield). If the game has it switched off altogether, switch it on for the textures that ask (the game's own textures are not changed).");
            try
            {
                var af = QualitySettings.anisotropicFiltering;
                if (aniso.Value && af == AnisotropicFiltering.Disable) QualitySettings.anisotropicFiltering = AnisotropicFiltering.Enable;
                Logger.LogInfo($"Texture filtering: anisotropic filtering was '{af}', now '{QualitySettings.anisotropicFiltering}'; cockpit sharpness {TexturedMaterials.CockpitSharpness:0.00}.");
            }
            catch (Exception e) { Logger.LogWarning("Texture filtering: " + e.Message); }
            var gunClear = Settings.Bind("Weapons", "GunClearOfAirframe", true,
                "The cannon's flash stays at the Typhoon's gun port, but its shells start further forward on the same line, beyond the base jet's (invisible) collision shapes, so they cannot hit the aircraft that fires them. " +
                "Off: the gun stays where the base jet has it relative to the hardpoint (safe, but not at the port).");
            HardpointStation.GunClearAirframe = gunClear.Value;
            gunClear.SettingChanged += (snd, arg) => { HardpointStation.GunClearAirframe = gunClear.Value; };
            var smooth = Settings.Bind("Cockpit", "DisplaySmoothness", 1f,
                "How often the cockpit displays are redrawn: 1 = attitude page and standby horizon 30 times a second, engine page and radar 24, map 20, read-outs 6. " +
                "2 doubles that (up to 60), 0.5 halves it. Higher costs frame rate.");
            TyphoonCockpit.DisplaySmoothness = Mathf.Clamp(smooth.Value, 0.25f, 2f);
            smooth.SettingChanged += (snd, arg) => { TyphoonCockpit.DisplaySmoothness = Mathf.Clamp(smooth.Value, 0.25f, 2f); };
            var sharp = Settings.Bind("Cockpit", "DisplaySharpness", 2,
                "2: the cockpit displays are drawn at twice the resolution (finer text and lines, most visible zoomed in). 1: as before 2.10.0. Takes effect at the next spawn.");
            MfdCanvas.Sharp = Mathf.Clamp(sharp.Value, 1, 2);
            sharp.SettingChanged += (snd, arg) => { MfdCanvas.Sharp = Mathf.Clamp(sharp.Value, 1, 2); };
            var keyLights = Settings.Bind("Cockpit", "KeyLights", true,
                "The lit legends on the panel keys follow the aircraft: a key is lit while what it stands for is on (radar, target camera, the page a display shows, " +
                "weapons live, defensive aids warning, gear and flight phase, night lighting, a chat message...) and shows a faint legend otherwise. Off: every legend lit, as before 2.9.0.");
            TyphoonCockpit.KeyLights = keyLights.Value;
            keyLights.SettingChanged += (snd, arg) => { TyphoonCockpit.KeyLights = keyLights.Value; };
            var chatDisp = Settings.Bind("Cockpit", "ChatOnKeypadDisplay", true,
                "The blue display of the left glareshield keypad shows the game's chat: the sender on the top line, the message under it (long ones a page at a time), " +
                "then back to the position read-out. Off: the read-out only.");
            var chatSecs = Settings.Bind("Cockpit", "ChatSeconds", 14f, "How long a chat message stays on the keypad display (5 - 60 s).");
            ChatFeed.Enabled = chatDisp.Value; ChatFeed.ShowSeconds = Mathf.Clamp(chatSecs.Value, 5f, 60f);
            chatDisp.SettingChanged += (snd, arg) => { ChatFeed.Enabled = chatDisp.Value; };
            chatSecs.SettingChanged += (snd, arg) => { ChatFeed.ShowSeconds = Mathf.Clamp(chatSecs.Value, 5f, 60f); };
            var dispBright = Settings.Bind("Cockpit", "DisplayBrightness", 1f, new ConfigDescription(
                "Brightness of the cockpit displays (1 = default; e.g. 1.4 = brighter, 0.7 = dimmer). Applied at once. At night they are dimmed further by DisplayNightBrightness.",
                new AcceptableValueRange<float>(0.3f, 3f)));
            TyphoonCockpit.DisplayBrightness = dispBright.Value;
            dispBright.SettingChanged += (snd, arg) => { TyphoonCockpit.DisplayBrightness = dispBright.Value; };
            DropOldSettings();
            StartCoroutine(_swap.Preload());
            StartCoroutine(TyphoonSounds.LoadAll(Path.Combine(Path.GetDirectoryName(typeof(TyphoonPlugin).Assembly.Location), "sounds"), Logger));
            SceneManager.sceneLoaded += (s, m) => _nextScan = 0f;
            Logger.LogInfo($"{Name} {Version} loaded; waiting for '{_baseAircraft.Value}'.");
        }

        void DropOldSettings()
        {
            if (Locked) return;
            try
            {
                var p = typeof(ConfigFile).GetProperty("OrphanedEntries", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                var d = p != null ? p.GetValue(Config, null) as System.Collections.IDictionary : null;
                if (d == null || d.Count == 0) return;
                int n = d.Count;
                d.Clear();
                Config.Save();
                Logger.LogInfo($"Config: {n} settings of earlier versions that are no longer used were removed from the file.");
            }
            catch (Exception e) { Logger.LogWarning("Config tidy-up skipped: " + e.Message); }
        }

        void Update()
        {
            if (!_enabled.Value) return;
            try { _swap.Tick(); }
            catch (Exception e) { Logger.LogError($"Typhoon model swap failed: {e}"); }

            if (Time.realtimeSinceStartup < _nextScan) return;
            _nextScan = Time.realtimeSinceStartup + 2f;
            try { Scan(); }
            catch (Exception e) { Logger.LogError($"Typhoon conversion failed: {e}"); }
        }

        void Scan()
        {
            foreach (var def in Resources.FindObjectsOfTypeAll<AircraftDefinition>())
            {
                if (def == null || _done.Contains(def)) continue;
                var parameters = def.aircraftParameters;
                string unitName = def.unitName ?? "";
                string paramName = parameters != null ? parameters.aircraftName ?? "" : "";
                if (!Matches(unitName) && !Matches(paramName)) continue;
                _done.Add(def);
                Convert(def, parameters, unitName);
            }
        }

        bool Matches(string name) =>
            name.Length > 0 && string.Equals(name.Trim(), _baseAircraft.Value.Trim(), StringComparison.OrdinalIgnoreCase);

        void Convert(AircraftDefinition def, AircraftParameters parameters, string originalName)
        {
            Logger.LogInfo($"Converting '{originalName}' into the {_displayName.Value}.");
            GameObject prefab = def.unitPrefab;
            if (prefab == null) Logger.LogWarning("Definition has no unitPrefab; only identity changes will apply.");

            if (_rename.Value)
            {
                def.unitName = _displayName.Value;
                def.description = _description.Value;
                if (parameters != null) parameters.aircraftName = _displayName.Value;
            }

            _swap.Register(def);
            Logger.LogInfo($"{_displayName.Value} ready. Flight performance: the base aircraft's own, unchanged (not adjustable).");
        }

        internal void EarlyHide(Aircraft a) { _swap?.EarlyHide(a); }
        internal void LogError(string msg) { Logger.LogError(msg); }
        internal void LogInfo(string msg) { Logger.LogInfo(msg); }

        internal static object GetMember(object obj, string name)
        {
            for (var t = obj.GetType(); t != null; t = t.BaseType)
            {
                var f = t.GetField(name, AllInstance | BindingFlags.DeclaredOnly);
                if (f != null) return f.GetValue(obj);
                var p = t.GetProperty(name, AllInstance | BindingFlags.DeclaredOnly);
                if (p != null && p.CanRead && p.GetIndexParameters().Length == 0) return p.GetValue(obj, null);
            }
            return null;
        }

    }

    [HarmonyPatch(typeof(Aircraft), "Awake")]
    static class AircraftAwakePatch
    {
        static void Postfix(Aircraft __instance)
        {
            try { TyphoonPlugin.Instance?.EarlyHide(__instance); }
            catch (Exception e) { TyphoonPlugin.Instance?.LogError("EarlyHide failed: " + e); }
        }
    }
}
