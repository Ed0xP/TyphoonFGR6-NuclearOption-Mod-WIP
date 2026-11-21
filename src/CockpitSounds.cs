using System;
using UnityEngine;

namespace TyphoonMod
{
    internal static class CockpitSounds
    {
        internal static bool Enabled = true;
        internal static float Volume = 0.5f;
        static AudioSource _one, _loop;
        static AudioClip _click, _clunk, _attn, _missile;
        const int Rate = 44100;

        static AudioClip Make(string name, float seconds, Func<float, float> f)
        {
            int n = Mathf.Max(1, (int)(Rate * seconds));
            var d = new float[n];
            for (int i = 0; i < n; i++) d[i] = Mathf.Clamp(f(i / (float)Rate), -1f, 1f);
            var c = AudioClip.Create(name, n, 1, Rate, false);
            c.SetData(d, 0);
            return c;
        }

        static bool Ensure()
        {
            if (!Enabled) return false;
            if (_one != null) return true;
            try
            {
                var rng = new System.Random(7);
                _click = Make("ty_click", 0.045f, t => (float)((rng.NextDouble() * 2 - 1) * 0.55 + Math.Sin(2 * Math.PI * 2600 * t) * 0.45) * Mathf.Exp(-t * 160f));
                _clunk = Make("ty_clunk", 0.22f, t => (float)(Math.Sin(2 * Math.PI * 130 * t) * Math.Exp(-t * 26) * 0.9 + (rng.NextDouble() * 2 - 1) * Math.Exp(-t * 80) * 0.35));
                _attn = Make("ty_attention", 0.62f, t =>
                {
                    float f = t < 0.30f ? 880f : 660f, tt = t < 0.30f ? t : t - 0.30f;
                    return (float)(Math.Sin(2 * Math.PI * f * t) * 0.5 + Math.Sin(2 * Math.PI * 2 * f * t) * 0.12) * Mathf.Exp(-tt * 7f) * Mathf.Clamp01(tt * 400f);
                });
                _missile = Make("ty_missile", 0.24f, t =>
                {
                    float f = ((int)(t / 0.06f) % 2 == 0) ? 1250f : 1700f, tt = t % 0.06f;
                    return (float)Math.Sin(2 * Math.PI * f * tt) * 0.45f * Mathf.Clamp01(tt * 600f) * Mathf.Clamp01((0.06f - tt) * 600f);
                });
                var go = new GameObject("TyphoonCockpitAudio");
                UnityEngine.Object.DontDestroyOnLoad(go);
                _one = go.AddComponent<AudioSource>();
                _loop = go.AddComponent<AudioSource>();
                foreach (var s in new[] { _one, _loop }) { s.spatialBlend = 0f; s.playOnAwake = false; s.dopplerLevel = 0f; s.priority = 60; }
                _loop.loop = true; _loop.clip = _missile;
                return true;
            }
            catch (Exception e) { Enabled = false; TyphoonPlugin.Instance?.LogError("Cockpit sounds: " + e.Message); return false; }
        }

        static void Play(AudioClip c, float gain) { if (Ensure() && c != null) _one.PlayOneShot(c, Mathf.Clamp01(Volume * gain)); }
        public static void Click() { Play(_click, 0.7f); }
        public static void Clunk() { Play(_clunk, 1.0f); }
        public static void Attention() { Play(_attn, 0.8f); }

        public static void Missile(bool on)
        {
            if (!on) { if (_loop != null && _loop.isPlaying) _loop.Stop(); return; }
            if (!Ensure()) return;
            _loop.volume = Mathf.Clamp01(Volume * 0.6f);
            if (!_loop.isPlaying) _loop.Play();
        }
    }
}
