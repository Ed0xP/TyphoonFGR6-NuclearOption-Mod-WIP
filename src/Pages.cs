using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace TyphoonMod
{
    internal static class MfdPages
    {
        internal sealed class EngineInfo
        {
            public float RpmL, RpmR, Throttle, Reheat, Nozzle, FuelKg, FuelLevel, FuelFlow;
            public bool Blink;
        }

        internal sealed class FlightInfo
        {
            public float Pitch, Roll, Heading, Speed, Mach, Altitude, Vs, Aoa, G, PosX, PosZ;
            public bool Gear, Airbrake;
            public string Weapon;
            public int Ammo;
        }

        static readonly Color32 Bg = new Color32(6, 9, 12, 255), Green = new Color32(70, 255, 110, 255), Cyan = new Color32(80, 225, 255, 255),
            White = new Color32(235, 240, 240, 255), Grey = new Color32(125, 135, 140, 255), Amber = new Color32(255, 190, 50, 255),
            Sky = new Color32(28, 86, 165, 255), Ground = new Color32(115, 76, 38, 255), Dim = new Color32(40, 50, 55, 255);

        internal sealed class StoreItem { public string Name; public int Ammo, Full; public bool Selected; }

        internal sealed class StoresInfo
        {
            public readonly System.Collections.Generic.List<StoreItem> Items = new System.Collections.Generic.List<StoreItem>();
            public string State = "SAFE";
            public float Flares = -1f;
            public bool Gear;
        }

        static readonly string[] LeftTabs = { "ENG", "FUEL", "HYD" }, RightTabs = { "FLT", "NAV", "WPN" };

        public static void Fuel(MfdCanvas c, EngineInfo e)
        {
            c.Clear(Bg);
            Tabs(c, LeftTabs, 1);
            bool low = e.FuelLevel < 0.15f;
            Color32 fc = low ? Amber : Cyan;
            float lv = Mathf.Clamp01(e.FuelLevel);
            float wing = Mathf.Clamp01((lv - 0.55f) / 0.45f), rear = Mathf.Clamp01((lv - 0.25f) / 0.30f), front = Mathf.Clamp01(lv / 0.25f);
            string[] nm = { "WING L", "FRONT", "REAR", "WING R" };
            float[] q = { wing, front, rear, wing };
            int bw = 36, gap = (c.W - 4 * bw) / 5, top = 52, h = 96;
            int ly = Math.Min(c.H - 74, top + h + 26);
            for (int i = 0; i < 4; i++)
            {
                int x = gap + i * (bw + gap);
                c.Box(x, top, bw, h, Grey, 1);
                int fh = Mathf.RoundToInt(q[i] * (h - 4));
                c.Fill(x + 2, top + h - 2 - fh, bw - 4, fh, q[i] < 0.12f ? Amber : fc);
                c.Text(Pct(q[i]), x + bw / 2 - Pct(q[i]).Length * 5, top + h + 4, White);
                c.Text(nm[i].Length > 5 ? nm[i].Substring(0, 4) + nm[i].Substring(nm[i].Length - 1) : nm[i], x - 6, top - 20, Grey);
            }
            c.Fill(8, ly, c.W - 16, 1, Dim);
            c.Text("TOTAL", 14, ly + 6, Grey);
            c.Text(Mathf.RoundToInt(e.FuelKg) + " KG", 76, ly + 6, fc);
            c.Text("FF", 14, ly + 25, Grey);
            c.Text(Mathf.RoundToInt(e.FuelFlow) + " KG/MIN", 76, ly + 25, White);
            c.Text("ENDUR", 14, ly + 44, Grey);
            c.Text(e.FuelFlow > 1f ? Mathf.Min(999, Mathf.RoundToInt(e.FuelKg / e.FuelFlow)) + " MIN" : "---", 76, ly + 44, low ? Amber : Green);
            if (low && e.Blink) c.Text("BINGO", c.W - 64, ly + 6, Amber);
        }

        public static void Hyd(MfdCanvas c, EngineInfo e, FlightInfo f)
        {
            c.Clear(Bg);
            Tabs(c, LeftTabs, 2);
            for (int i = 0; i < 2; i++)
            {
                float rpm = Mathf.Clamp01(i == 0 ? e.RpmL : e.RpmR);
                float p = Mathf.Clamp01(rpm / 0.35f);
                int bar = Mathf.RoundToInt(p * 280f);
                int x = 20 + i * (c.W / 2), y = 40;
                c.Text(i == 0 ? "SYS 1" : "SYS 2", x, y, Grey);
                c.Text(bar.ToString("000"), x, y + 20, p > 0.8f ? Green : Amber, 2);
                c.Text("BAR", x + 66, y + 34, Grey);
                c.Box(x, y + 58, 96, 10, Grey, 1);
                c.Fill(x + 2, y + 60, Mathf.RoundToInt(92 * p), 6, p > 0.8f ? Green : Amber);
            }
            c.Fill(8, 128, c.W - 16, 1, Dim);
            string[] lab = { "GEAR", "AIRBRAKE", "NWS", "BRAKES", "FCS" };
            string[] val = { f.Gear ? "DOWN" : "UP", f.Airbrake ? "OUT" : "IN", f.Gear ? "ON" : "OFF", "NORM", "NORM" };
            for (int i = 0; i < lab.Length; i++)
            {
                int y = 138 + i * 22;
                c.Text(lab[i], 14, y, Grey);
                bool amber = (i == 1 && f.Airbrake);
                c.Text(val[i], 130, y, amber ? Amber : Green);
            }
        }

        internal sealed class MapInfo
        {
            public Color32[] Grid;
            public int N;
            public float X0, Z0, Cell, PosX, PosZ, RangeM = 18520f;
            public System.Collections.Generic.List<MapField> Fields;
        }

        internal sealed class MapField { public string Name; public float X, Z; public float[] Rwy; }

        public static void Map(MfdCanvas c, FlightInfo f, MapInfo m)
        {
            if (m == null || m.Grid == null) { Nav(c, f); return; }
            c.Clear(Bg);
            float cx = c.W * 0.5f, cy = c.H * 0.70f;
            float mpp = m.RangeM / (c.H * 0.58f);
            float h = f.Heading * Mathf.Deg2Rad, sh = Mathf.Sin(h), ch = Mathf.Cos(h);
            float inv = 1f / m.Cell;
            int N = m.N;
            for (int py = 24; py < c.H; py++)
            {
                float dy = (cy - py) * mpp;
                for (int px = 0; px < c.W; px++)
                {
                    float dx = (px - cx) * mpp;
                    float e = m.PosX + dx * ch + dy * sh, n = m.PosZ - dx * sh + dy * ch;
                    int ix = (int)((e - m.X0) * inv), iz = (int)((n - m.Z0) * inv);
                    if ((uint)ix >= (uint)N || (uint)iz >= (uint)N) continue;
                    var col = m.Grid[iz * N + ix];
                    if (col.a == 0) continue;
                    c.Set(px, py, col);
                }
            }
            const float G = 10000f;
            for (int k = -4; k <= 4; k++)
            {
                float gx = Mathf.Floor(m.PosX / G) * G + k * G, gz = Mathf.Floor(m.PosZ / G) * G + k * G;
                GridLine(c, f, m, cx, cy, mpp, gx, m.PosZ - 5 * G, gx, m.PosZ + 5 * G);
                GridLine(c, f, m, cx, cy, mpp, m.PosX - 5 * G, gz, m.PosX + 5 * G, gz);
            }
            if (m.Fields != null)
                foreach (var fl in m.Fields)
                {
                    float fx, fy;
                    ToScreen(f, m, cx, cy, mpp, fl.X, fl.Z, out fx, out fy);
                    if (fx < -40 || fx > c.W + 40 || fy < 20 || fy > c.H + 40) continue;
                    for (int k = 0; k + 3 < fl.Rwy.Length; k += 4)
                    {
                        float ax, ay, bx, by;
                        ToScreen(f, m, cx, cy, mpp, fl.Rwy[k], fl.Rwy[k + 1], out ax, out ay);
                        ToScreen(f, m, cx, cy, mpp, fl.Rwy[k + 2], fl.Rwy[k + 3], out bx, out by);
                        c.Line(ax, ay, bx, by, White, 2);
                    }
                    c.Circle(fx, fy, 9f, Cyan);
                    if (!string.IsNullOrEmpty(fl.Name) && fy > 50 && fy < c.H - 4)
                    {
                        string nm = fl.Name.Length > 10 ? fl.Name.Substring(0, 10) : fl.Name;
                        c.Text(nm, Mathf.RoundToInt(fx + 12), Mathf.RoundToInt(fy - 8), Cyan);
                    }
                }
            float r1 = m.RangeM / mpp;
            c.Circle(cx, cy, r1 * 0.5f, Grey);
            c.Circle(cx, cy, r1, White);
            for (int d = 0; d < 360; d += 10)
            {
                float a = (d - f.Heading) * Mathf.Deg2Rad;
                float s = Mathf.Sin(a), co = -Mathf.Cos(a);
                float len = d % 30 == 0 ? 9f : 4f;
                c.Line(cx + s * r1, cy + co * r1, cx + s * (r1 - len), cy + co * (r1 - len), White, 1);
                if (d % 90 == 0)
                {
                    string t = d == 0 ? "N" : d == 90 ? "E" : d == 180 ? "S" : "W";
                    c.Text(t, Mathf.RoundToInt(cx + s * (r1 - 20) - 5), Mathf.RoundToInt(cy + co * (r1 - 20) - 8), Cyan);
                }
            }
            c.Line(cx, cy - 12, cx, cy + 10, White, 2);
            c.Line(cx - 11, cy - 2, cx + 11, cy - 2, White, 2);
            c.Line(cx - 5, cy + 9, cx + 5, cy + 9, White, 2);
            c.Line(cx, cy - 14, cx, cy - r1, Green, 1);
            c.Fill(0, 0, c.W, 24, Bg);
            Tabs(c, RightTabs, 1);
            string hd = (Mathf.RoundToInt(f.Heading) % 360).ToString("000");
            c.Fill(Mathf.RoundToInt(cx) - 21, 26, 42, 20, Bg); c.Box(Mathf.RoundToInt(cx) - 21, 26, 42, 20, White, 1);
            c.Text(hd, Mathf.RoundToInt(cx) - 15, 28, White);
            c.Fill(2, 26, 52, 40, Bg);
            c.Text(Mathf.RoundToInt(f.Speed * 1.944f) + "KT", 4, 28, Cyan);
            c.Text(Mathf.RoundToInt(f.Altitude * 3.281f / 100f).ToString("000"), 4, 46, Cyan);
            string rng = Mathf.RoundToInt(m.RangeM / 1852f) + "NM";
            c.Fill(c.W - 4 - rng.Length * 10, 26, rng.Length * 10 + 2, 18, Bg);
            c.Text(rng, c.W - 3 - rng.Length * 10, 28, White);
            c.Text("TRK", c.W - 34, c.H - 20, Grey);
        }

        static void GridLine(MfdCanvas c, FlightInfo f, MapInfo m, float cx, float cy, float mpp, float x0, float z0, float x1, float z1)
        {
            float h = f.Heading * Mathf.Deg2Rad, sh = Mathf.Sin(h), ch = Mathf.Cos(h);
            float ex0 = x0 - m.PosX, nz0 = z0 - m.PosZ, ex1 = x1 - m.PosX, nz1 = z1 - m.PosZ;
            float ax = cx + (ex0 * ch - nz0 * sh) / mpp, ay = cy - (ex0 * sh + nz0 * ch) / mpp;
            float bx = cx + (ex1 * ch - nz1 * sh) / mpp, by = cy - (ex1 * sh + nz1 * ch) / mpp;
            c.Line(ax, ay, bx, by, MapGrid, 1);
        }

        static void ToScreen(FlightInfo f, MapInfo m, float cx, float cy, float mpp, float x, float z, out float sx, out float sy)
        {
            float h = f.Heading * Mathf.Deg2Rad, sh = Mathf.Sin(h), ch = Mathf.Cos(h);
            float e = x - m.PosX, n = z - m.PosZ;
            sx = cx + (e * ch - n * sh) / mpp; sy = cy - (e * sh + n * ch) / mpp;
        }

        static readonly Color32 MapGrid = new Color32(60, 95, 170, 255);

        public static void Nav(MfdCanvas c, FlightInfo f)
        {
            c.Clear(Bg);
            Tabs(c, RightTabs, 1);
            float cx = c.W * 0.5f, cy = c.H * 0.56f, r = Mathf.Min(c.W, c.H) * 0.34f;
            c.Circle(cx, cy, r, Grey);
            for (int d = 0; d < 360; d += 10)
            {
                float a = (d - f.Heading) * Mathf.Deg2Rad;
                float s = Mathf.Sin(a), co = -Mathf.Cos(a);
                float len = d % 30 == 0 ? 10f : 5f;
                c.Line(cx + s * r, cy + co * r, cx + s * (r - len), cy + co * (r - len), d % 90 == 0 ? White : Grey, 1);
                if (d % 30 == 0)
                {
                    string t = d == 0 ? "N" : d == 90 ? "E" : d == 180 ? "S" : d == 270 ? "W" : (d / 10).ToString();
                    c.Text(t, Mathf.RoundToInt(cx + s * (r - 24) - t.Length * 5), Mathf.RoundToInt(cy + co * (r - 24) - 8), d % 90 == 0 ? Cyan : Grey);
                }
            }
            c.Line(cx, cy - r - 8, cx, cy - r + 12, White, 2);
            c.Line(cx, cy - 12, cx, cy + 12, Green, 2);
            c.Line(cx - 12, cy, cx + 12, cy, Green, 2);
            c.Line(cx - 5, cy + 10, cx + 5, cy + 10, Green, 2);
            string hd = (Mathf.RoundToInt(f.Heading) % 360).ToString("000");
            c.Box(Mathf.RoundToInt(cx) - 20, 26, 40, 20, White, 1);
            c.Text(hd, Mathf.RoundToInt(cx) - 15, 28, White);
            c.Text("GS", 6, 28, Grey); c.Text(Mathf.RoundToInt(f.Speed * 1.944f).ToString(), 6, 46, Cyan);
            c.Text("ALT", c.W - 50, 28, Grey); c.Text(Mathf.RoundToInt(f.Altitude * 3.281f / 100f).ToString("000"), c.W - 50, 46, Cyan);
            c.Text("M" + f.Mach.ToString("0.00", CultureInfo.InvariantCulture), 6, c.H - 20, Grey);
        }

        public static void Stores(MfdCanvas c, StoresInfo s)
        {
            c.Clear(Bg);
            Tabs(c, RightTabs, 2);
            int y = 30, n = 0;
            foreach (var it in s.Items)
            {
                if (n++ >= 8) break;
                Color32 col = it.Ammo <= 0 ? Grey : it.Selected ? White : Green;
                if (it.Selected) c.Box(6, y - 2, c.W - 12, 20, Cyan, 1);
                string nm = it.Name.Length > 14 ? it.Name.Substring(0, 14) : it.Name;
                c.Text(nm, 12, y, col);
                string a = it.Ammo.ToString();
                c.Text(a, c.W - 16 - a.Length * 10, y, it.Ammo <= 0 ? Amber : col);
                y += 23;
            }
            if (s.Items.Count == 0) c.Text("NO STORES", 12, y, Grey);
            c.Fill(8, c.H - 48, c.W - 16, 1, Dim);
            bool armed = s.State == "READY" || s.State == "RELOAD";
            c.Text("MASTER ARM", 10, c.H - 42, Grey);
            c.Text(armed ? "LIVE" : "SAFE", 126, c.H - 42, armed ? Amber : Green);
            if (s.Flares >= 0f) { c.Text("FLARES", 10, c.H - 22, Grey); c.Text(Pct(s.Flares) + "%", 126, c.H - 22, s.Flares < 0.2f ? Amber : Green); }
        }

        static void Tabs(MfdCanvas c, string[] labels, int active)
        {
            int n = labels.Length, w = c.W / n;
            for (int i = 0; i < n; i++)
            {
                int x = i * w + w / 2 - labels[i].Length * 5;
                if (i == active) { c.Fill(x - 4, 3, labels[i].Length * 10 + 8, 18, Cyan); c.Text(labels[i], x, 4, Bg); }
                else c.Text(labels[i], x, 4, Grey);
            }
            for (int i = 0; i < 5; i++) { c.Fill(0, 48 + i * 40, 5, 2, Dim); c.Fill(c.W - 5, 48 + i * 40, 5, 2, Dim); }
        }

        static string Pct(float v) { return Mathf.RoundToInt(v * 100f).ToString(CultureInfo.InvariantCulture); }

        public static void Engine(MfdCanvas c, EngineInfo e)
        {
            c.Clear(Bg);
            Tabs(c, new[] { "ENG", "FUEL", "HYD" }, 0);
            c.Text("NH %", 34, 28, Grey);
            for (int i = 0; i < 2; i++)
            {
                int x = 24 + i * 50, top = 66, h = 104;
                float v = Mathf.Clamp01(i == 0 ? e.RpmL : e.RpmR);
                c.Box(x, top, 26, h, Grey, 1);
                int fh = Mathf.RoundToInt(v * (h - 4));
                c.Fill(x + 2, top + h - 2 - fh, 22, fh, v > 0.97f ? Amber : Green);
                c.Fill(x - 5, top + Mathf.RoundToInt(0.4f * h), 4, 2, White);
                c.Text(i == 0 ? "L" : "R", x + 8, top + h + 2, White);
                c.Text(Mathf.RoundToInt(v * 100f).ToString("000"), x - 2, top + h + 20, Green);
                if (e.Reheat > 0.05f) { c.Fill(x - 4, top - 20, 34, 17, Amber); c.Text("RHT", x - 2, top - 20, Bg); }
            }
            int rx = 136;
            c.Text("THR", rx, 30, Grey);
            c.Text(Pct(e.Throttle) + "%", rx, 48, White, 2);
            c.Text("NOZ", rx, 92, Grey);
            c.Text(Pct(e.Nozzle) + "%", rx + 46, 92, Cyan);
            c.Box(rx, 112, 104, 10, Grey, 1);
            c.Fill(rx + 2, 114, Mathf.RoundToInt(100 * Mathf.Clamp01(e.Nozzle)), 6, Cyan);
            c.Text("REHEAT", rx, 134, Grey);
            c.Text(e.Reheat > 0.05f ? Pct(e.Reheat) + "%" : "OFF", rx, 152, e.Reheat > 0.05f ? Amber : Grey);
            bool low = e.FuelLevel < 0.15f;
            c.Fill(8, 210, c.W - 16, 1, Dim);
            c.Text("FUEL", 10, 216, Grey);
            c.Text(Mathf.RoundToInt(e.FuelKg) + " KG", 62, 216, low ? Amber : Cyan);
            if (low && e.Blink) c.Text("BINGO", 196, 216, Amber);
            c.Box(10, 238, 110, 10, Grey, 1);
            c.Fill(12, 240, Mathf.RoundToInt(106 * Mathf.Clamp01(e.FuelLevel)), 6, low ? Amber : Cyan);
            c.Text("FF " + Mathf.RoundToInt(e.FuelFlow), 132, 235, Grey);
        }

        public static void Flight(MfdCanvas c, FlightInfo f)
        {
            c.Clear(Bg);
            Tabs(c, new[] { "FLT", "NAV", "WPN" }, 0);
            int bx = 70, by = 30, bw = 116, bh = 104;
            float k = 2.2f, rr = f.Roll * Mathf.Deg2Rad, sr = Mathf.Sin(rr), cr = Mathf.Cos(rr);
            float cx = bx + bw * 0.5f, cy = by + bh * 0.5f;
            for (int y = by; y < by + bh; y++)
                for (int x = bx; x < bx + bw; x++)
                {
                    float dx = x - cx, dy = y - cy;
                    float up = -dx * sr - dy * cr;
                    c.Set(x, y, up > -f.Pitch * k ? Sky : Ground);
                }
            int p0 = Mathf.FloorToInt((f.Pitch - 25f) / 10f) * 10;
            for (int a = p0; a <= f.Pitch + 25f; a += 10)
            {
                if (a < -90 || a > 90) continue;
                float off = (a - f.Pitch) * k;
                float px = cx - sr * off, py = cy - cr * off;
                float half = a == 0 ? 80f : 20f;
                float ex = cr * half, ey = -sr * half;
                c.Line(px - ex, py - ey, px + ex, py + ey, White, a == 0 ? 2 : 1, bx, by, bx + bw, by + bh);
                if (a != 0)
                {
                    float lx = px + ex + cr * 4f, ly = py + ey - sr * 4f;
                    string lab = Mathf.Abs(a).ToString();
                    if (lx > bx && lx < bx + bw - 20 && ly > by && ly < by + bh - 14) c.Text(lab, Mathf.RoundToInt(lx), Mathf.RoundToInt(ly) - 8, White);
                }
            }
            c.Line(cx - 28, cy, cx - 10, cy, Amber, 3); c.Line(cx + 10, cy, cx + 28, cy, Amber, 3);
            c.Line(cx - 10, cy, cx - 5, cy + 6, Amber, 2); c.Line(cx - 5, cy + 6, cx, cy, Amber, 2);
            c.Line(cx, cy, cx + 5, cy + 6, Amber, 2); c.Line(cx + 5, cy + 6, cx + 10, cy, Amber, 2);
            c.Box(bx, by, bw, bh, Grey, 1);
            c.Text("CAS", 10, 36, Grey);
            c.Box(4, 54, 60, 22, White, 1);
            c.Text(Mathf.RoundToInt(f.Speed * 1.94384f).ToString(CultureInfo.InvariantCulture), 10, 57, White);
            c.Text("M" + f.Mach.ToString("0.00", CultureInfo.InvariantCulture), 8, 84, Cyan);
            c.Text("ALT", 196, 36, Grey);
            c.Box(190, 54, 62, 22, White, 1);
            c.Text((Mathf.RoundToInt(f.Altitude * 3.28084f / 10f) * 10).ToString(CultureInfo.InvariantCulture), 194, 57, White);
            c.Text("VS", 196, 84, Grey);
            c.Text((Mathf.RoundToInt(f.Vs * 196.85f / 100f) * 100).ToString(CultureInfo.InvariantCulture), 194, 102, Cyan);
            int ty = 152;
            c.Fill(30, ty + 18, 196, 1, Grey);
            for (int h = Mathf.FloorToInt((f.Heading - 45f) / 5f) * 5; h <= f.Heading + 45f; h += 5)
            {
                float x = 128f + (h - f.Heading) * 2.1f;
                if (x < 30 || x > 226) continue;
                int hh = ((h % 360) + 360) % 360;
                bool major = hh % 10 == 0;
                c.Fill(Mathf.RoundToInt(x), ty + (major ? 8 : 12), 1, major ? 10 : 6, White);
                if (hh % 30 == 0 && Mathf.Abs(x - 128f) > 26f) c.Text((hh / 10).ToString("00"), Mathf.RoundToInt(x) - 10, ty - 10, White);
            }
            c.Fill(106, ty - 12, 44, 22, Bg); c.Box(106, ty - 12, 44, 22, White, 1);
            c.Text((Mathf.RoundToInt(f.Heading) % 360).ToString("000"), 113, ty - 9, White);
            c.Line(128, ty + 18, 124, ty + 26, White, 1); c.Line(128, ty + 18, 132, ty + 26, White, 1);
            c.Text("G " + f.G.ToString("0.0", CultureInfo.InvariantCulture), 10, 186, White);
            c.Text("AOA " + Mathf.RoundToInt(f.Aoa), 150, 186, f.Aoa > 20f ? Amber : White);
            c.Fill(8, 208, c.W - 16, 1, Dim);
            c.Text(f.Gear ? "GEAR DN" : "GEAR UP", 10, 214, f.Gear ? Green : Grey);
            if (f.Airbrake) { c.Fill(150, 212, 50, 19, Amber); c.Text("ABRK", 155, 213, Bg); }
            if (!string.IsNullOrEmpty(f.Weapon))
            {
                string n = f.Weapon.Length > 14 ? f.Weapon.Substring(0, 14) : f.Weapon;
                c.Text(n + " " + f.Ammo, 10, 236, Cyan);
            }
        }

        public static void Tac(MfdCanvas c, FlightInfo f)
        {
            c.Clear(Bg);
            Tabs(c, new[] { "TAC", "MAP", "DAS" }, 0);
            float cx = 128, cy = 146, R = 92;
            c.Circle(cx, cy, R, Grey); c.Circle(cx, cy, R * 0.5f, Dim);
            for (int a = 0; a < 360; a += 30)
            {
                float ang = (a - f.Heading) * Mathf.Deg2Rad;
                float sx = Mathf.Sin(ang), sy = -Mathf.Cos(ang);
                c.Line(cx + sx * (R - 8), cy + sy * (R - 8), cx + sx * R, cy + sy * R, White, 1);
                string lab = a == 0 ? "N" : a == 90 ? "E" : a == 180 ? "S" : a == 270 ? "W" : (a / 10).ToString();
                c.Text(lab, Mathf.RoundToInt(cx + sx * (R - 22)) - lab.Length * 5, Mathf.RoundToInt(cy + sy * (R - 22)) - 8, a % 90 == 0 ? Cyan : Grey);
            }
            c.Line(cx, cy - 10, cx, cy + 8, Green, 2); c.Line(cx - 9, cy, cx + 9, cy, Green, 2); c.Line(cx - 4, cy + 7, cx + 4, cy + 7, Green, 2);
            c.Text("RDR STBY", 88, 28, Grey);
        }

        internal sealed class RadarContact
        {
            public float Az, RangeM, AltFt, Vx, Vz;
            public int Side;
            public int Kind;
            public bool Selected;
            public string Name;
        }

        internal sealed class RadarInfo
        {
            public bool On, MissileWarn, Blink, Spike;
            public float Heading, RadarRangeM, OwnSpeed;
            public readonly System.Collections.Generic.List<RadarContact> Contacts = new System.Collections.Generic.List<RadarContact>();
        }

        static readonly Color32 RdrRed = new Color32(255, 70, 55, 255), RdrYel = new Color32(255, 220, 60, 255), RdrGrid = new Color32(30, 70, 45, 255),
            RdrFaint = new Color32(20, 46, 30, 255);
        static readonly float[] RangeSteps = { 5f, 10f, 20f, 40f, 80f, 160f };

        public static void Radar(MfdCanvas c, RadarInfo r)
        {
            c.Clear(Bg);
            int W = c.W, H = c.H;
            const float AZ = 60f;
            int x0 = 32, x1 = W - 12, y0 = 26, y1 = H - 50;
            float cx = (x0 + x1) * 0.5f, hw = (x1 - x0) * 0.5f, ht = y1 - y0;
            RadarContact sel = null;
            foreach (var k in r.Contacts) if (k.Selected) { sel = k; break; }
            float baseNm = r.RadarRangeM > 100f ? r.RadarRangeM / 1852f : 40f;
            float far = 0f;
            foreach (var k in r.Contacts) if (Mathf.Abs(k.Az) <= AZ) far = Mathf.Max(far, k.RangeM / 1852f);
            float want = sel != null ? Mathf.Max(sel.RangeM / 1852f * 1.3f, 5f) : far > 0f ? Mathf.Max(far * 1.2f, 5f) : baseNm;
            float scale = RangeSteps[RangeSteps.Length - 1];
            foreach (var st in RangeSteps) if (st >= want) { scale = st; break; }
            for (int q = 1; q < 4; q++)
            {
                int y = Mathf.RoundToInt(y1 - ht * q / 4f);
                for (int x = x0; x < x1; x += 6) c.Fill(x, y, 3, 1, RdrFaint);
            }
            for (int a = -60; a <= 60; a += 30)
            {
                int x = Mathf.RoundToInt(cx + hw * a / AZ);
                if (a != -60 && a != 60) for (int y = y0; y < y1; y += 6) c.Fill(x, y, 1, 3, a == 0 ? RdrGrid : RdrFaint);
                c.Fill(x, y1, 1, 5, Grey);
                string lab = Math.Abs(a).ToString();
                if (a != 0) c.Text(lab, x - lab.Length * 5, y1 + 5, Dim);
            }
            c.Box(x0, y0, x1 - x0 + 1, (int)ht + 1, RdrGrid, 1);
            string sTop = ((int)scale).ToString(), sMid = (scale / 2f % 1f == 0f ? ((int)(scale / 2f)).ToString() : (scale / 2f).ToString("0.#", CultureInfo.InvariantCulture));
            c.Text(sTop, Math.Max(0, x0 - 3 - sTop.Length * 10), y0 - 2, Grey);
            c.Text(sMid, Math.Max(0, x0 - 3 - sMid.Length * 10), Mathf.RoundToInt(y1 - ht / 2f) - 8, Dim);
            c.Text(r.On ? "RWS" : "STBY", 4, 4, r.On ? Green : Amber);
            int hdg = Mathf.RoundToInt(r.Heading) % 360; if (hdg < 0) hdg += 360;
            string hs = hdg.ToString("000");
            c.Box(Mathf.RoundToInt(cx) - 19, 2, 38, 20, White, 1);
            c.Text(hs, Mathf.RoundToInt(cx) - 15, 4, White);
            if (r.MissileWarn && r.Blink) { c.Fill(x1 - 74, y0 + 3, 70, 20, RdrRed); c.Text("MISSILE", x1 - 72, y0 + 5, Bg); }
            else if (r.Spike && r.Blink) c.Text("SPIKE", x1 - 54, y0 + 4, Amber);
            c.Line(cx, y1 - 2, cx, y1 - 13, Cyan, 2); c.Line(cx - 8, y1 - 8, cx + 8, y1 - 8, Cyan, 2); c.Line(cx - 4, y1 - 2, cx + 4, y1 - 2, Cyan, 2);
            if (!r.On) c.Text("RADAR STBY", Mathf.RoundToInt(cx) - 50, Mathf.RoundToInt(y0 + ht / 2f) - 8, Amber);
            {
                if (r.On)
                {
                    float t = Time.unscaledTime * 1.3f;
                    float sa = Mathf.Sin(t) * AZ;
                    int sx = Mathf.RoundToInt(cx + hw * sa / AZ);
                    for (int y = y0 + 2; y < y1 - 1; y += 2) c.Set(sx, y, RdrGrid);
                    c.Fill(sx - 3, y1 + 1, 7, 3, Green);
                }
                for (int pass = 0; pass < 2; pass++)
                    foreach (var k in r.Contacts)
                    {
                        if (k.Selected != (pass == 1)) continue;
                        Color32 col = k.Side > 0 ? Green : k.Side < 0 ? RdrRed : RdrYel;
                        if (Mathf.Abs(k.Az) > AZ || k.RangeM / 1852f > scale)
                        {
                            float ex = cx + hw * Mathf.Clamp(k.Az, -AZ, AZ) / AZ;
                            float ey = k.RangeM / 1852f > scale ? y0 + 4 : y1 - ht * Mathf.Min(k.RangeM / 1852f / scale, 1f);
                            int ix = Mathf.RoundToInt(Mathf.Clamp(ex, x0 + 4, x1 - 4)), iy = Mathf.RoundToInt(Mathf.Clamp(ey, y0 + 4, y1 - 4));
                            if (k.Az < -AZ) { c.Line(ix + 4, iy - 4, ix, iy, col, 2); c.Line(ix, iy, ix + 4, iy + 4, col, 2); }
                            else if (k.Az > AZ) { c.Line(ix - 4, iy - 4, ix, iy, col, 2); c.Line(ix, iy, ix - 4, iy + 4, col, 2); }
                            else { c.Line(ix - 4, iy + 4, ix, iy, col, 2); c.Line(ix, iy, ix + 4, iy + 4, col, 2); }
                            continue;
                        }
                        float px = cx + hw * k.Az / AZ, py = y1 - ht * (k.RangeM / 1852f) / scale;
                        Symbol(c, px, py, k, col);
                        if (k.Kind != 1)
                        {
                            float vl = Mathf.Sqrt(k.Vx * k.Vx + k.Vz * k.Vz);
                            if (vl > 15f)
                            {
                                float len = Mathf.Clamp(vl / 12f, 8f, 30f), ux = k.Vx / vl, uz = k.Vz / vl;
                                c.Line(px + ux * 6f, py - uz * 6f, px + ux * (6f + len), py - uz * (6f + len), col, 2, x0, y0, x1, y1);
                            }
                            if (k.Kind == 0)
                            {
                                string al = Mathf.Clamp(Mathf.RoundToInt(k.AltFt / 1000f), 0, 99).ToString();
                                float side = k.Vx > 0f ? -1f : 1f;
                                c.Text(al, Mathf.RoundToInt(px + side * 9f - (side < 0 ? al.Length * 10 : 0)), Mathf.RoundToInt(py) - 2, col);
                            }
                        }
                        if (k.Selected)
                        {
                            c.Circle(px, py, 10f, White);
                            c.Line(px, py - 13, px, py - 10, White, 1); c.Line(px, py + 10, px, py + 13, White, 1);
                        }
                    }
                int n = r.Contacts.Count;
                if (n == 0 && r.On) c.Text("NO TRACKS", Mathf.RoundToInt(cx) - 45, y0 + 6, Dim);
            }
            int by = H - 22;
            c.Fill(4, by - 4, W - 8, 1, Dim);
            if (sel != null)
            {
                string nm = (sel.Name ?? "TGT").ToUpperInvariant();
                if (nm.Length > 9) nm = nm.Substring(0, 9);
                Color32 col = sel.Side > 0 ? Green : sel.Side < 0 ? RdrRed : RdrYel;
                float rn = sel.RangeM / 1852f;
                string rs = rn < 10f ? rn.ToString("0.0", CultureInfo.InvariantCulture) : Mathf.RoundToInt(rn).ToString();
                c.Text(nm, 4, by, col);
                c.Text(rs + "NM", 100, by, White);
                if (sel.Kind == 0) c.Text(Mathf.RoundToInt(sel.AltFt / 100f).ToString("000") , W - 40, by, Cyan);
                else c.Text("SFC", W - 34, by, Cyan);
            }
            else if (r.On) c.Text(r.Contacts.Count + " TRK", 4, by, Grey);
        }

        static void Symbol(MfdCanvas c, float x, float y, RadarContact k, Color32 col)
        {
            int ix = Mathf.RoundToInt(x), iy = Mathf.RoundToInt(y);
            if (k.Kind == 2) { c.Line(ix - 4, iy - 4, ix + 4, iy + 4, col, 2); c.Line(ix - 4, iy + 4, ix + 4, iy - 4, col, 2); return; }
            if (k.Side < 0)
            {
                c.Line(ix - 5, iy + 4, ix, iy - 5, col, 2); c.Line(ix, iy - 5, ix + 5, iy + 4, col, 2);
                if (k.Kind == 0) c.Line(ix - 5, iy + 4, ix + 5, iy + 4, col, 2);
            }
            else if (k.Side > 0)
            {
                if (k.Kind == 0) { c.Circle(x, y, 4.5f, col); c.Circle(x, y, 3.5f, col); }
                else for (int i = 0; i <= 12; i++) { float a = Mathf.PI * i / 12f; c.Fill(Mathf.RoundToInt(x - Mathf.Cos(a) * 5f), Mathf.RoundToInt(y - Mathf.Sin(a) * 5f), 2, 2, col); }
            }
            else
            {
                c.Fill(ix - 4, iy - 4, 9, 2, col); c.Fill(ix - 4, iy - 4, 2, 9, col); c.Fill(ix + 3, iy - 4, 2, 9, col);
                if (k.Kind == 0) c.Fill(ix - 4, iy + 3, 9, 2, col);
            }
        }

        internal sealed class TargetInfo
        {
            public string Weapon, State;
            public int Targets;
            public bool Laser, Lasing, HasEnvelope, MissileWarn, RadarLock, Spike, Blink;
            public float Min, Max, NoEscape = -1f, Range = -1f, Tof = -1f, OffAz, OffEl;
        }

        static readonly Color32 Red = new Color32(255, 60, 50, 255), DarkGreen = new Color32(20, 95, 45, 255), BrightGreen = new Color32(60, 210, 95, 255);

        static int TextWidth(string s) { return (s ?? "").Length * 10; }

        public static void TargetTop(MfdCanvas c, TargetInfo t)
        {
            c.Clear(Bg);
            int H = c.H;
            if (t.MissileWarn && t.Blink) { c.Fill(0, 0, c.W, H, Red); c.Text("MISSILE", (c.W - 70) / 2, (H - 16) / 2, Bg); return; }
            if (t.RadarLock && t.Blink) { c.Fill(0, 0, c.W, H, Amber); c.Text("RADAR LOCK", (c.W - 100) / 2, (H - 16) / 2, Bg); return; }
            string w = string.IsNullOrEmpty(t.Weapon) ? "NO WPN" : t.Weapon;
            Color32 sc = t.State == "READY" ? Green : t.State == "SAFE" ? Grey : t.State == "EMPTY" ? Red : Amber;
            string st = t.State ?? "";
            bool two = H >= 38;
            int y1 = two ? 2 : (H - 16) / 2;
            int maxName = (c.W - 16 - TextWidth(st) - (two ? 0 : 60)) / 10;
            if (w.Length > maxName) w = w.Substring(0, Math.Max(1, maxName));
            c.Text(w, 6, y1, Cyan);
            c.Text(st, c.W - 6 - TextWidth(st), y1, sc);
            string tg = "TGT " + t.Targets;
            if (!two) { c.Text(tg, c.W - 16 - TextWidth(st) - TextWidth(tg), y1, White); return; }
            int y2 = H - 18;
            c.Text(tg, 6, y2, t.Targets > 0 ? White : Grey);
            if (t.Laser) { string l = t.Lasing ? "LASING" : "NO LASE"; c.Text(l, c.W - 6 - TextWidth(l), y2, t.Lasing ? Green : Amber); }
            else if (t.Spike) c.Text("RWR", c.W - 36, y2, Amber);
        }

        public static void TargetBottom(MfdCanvas c, TargetInfo t)
        {
            c.Clear(Bg);
            int H = c.H;
            if (t.Range < 0f) { c.Text("NO TARGET", (c.W - 90) / 2, (H - 16) / 2, Grey); return; }
            bool two = H >= 38;
            string cue = null; Color32 cc = Grey;
            if (t.HasEnvelope && t.Max > 0f)
            {
                if (t.Range < t.Min) { cue = "MIN RNG"; cc = Amber; }
                else if (t.NoEscape > 0f && t.Range <= t.NoEscape) { cue = "NEZ"; cc = BrightGreen; }
                else if (t.Range <= t.Max) { cue = "IN RNG"; cc = Green; }
                else { cue = "OUT RNG"; cc = Grey; }
            }
            if (two)
            {
                int x0 = 6, x1 = c.W - 6, by = 6, bh = 9;
                if (t.HasEnvelope && t.Max > 0f)
                {
                    float scale = Math.Max(t.Max * 1.15f, t.Range * 1.05f);
                    Func<float, int> X = v => x0 + (int)Math.Round((x1 - x0) * Mathf.Clamp01(v / scale));
                    c.Fill(x0, by, x1 - x0, bh, Dim);
                    c.Fill(X(t.Min), by, X(t.Max) - X(t.Min), bh, DarkGreen);
                    if (t.NoEscape > t.Min) c.Fill(X(t.Min), by, X(Math.Min(t.NoEscape, t.Max)) - X(t.Min), bh, BrightGreen);
                    int mx = X(t.Range);
                    c.Fill(mx - 1, by - 4, 3, bh + 8, White);
                }
                else
                {
                    string rng = "RNG " + (t.Range / 1000f).ToString("0.0", CultureInfo.InvariantCulture) + " KM";
                    c.Text(rng, 6, 2, White);
                }
            }
            int y = two ? H - 18 : (H - 16) / 2;
            if (cue != null)
            {
                if (cue == "NEZ") { c.Fill(4, y - 1, TextWidth(cue) + 6, 18, cc); c.Text(cue, 7, y, Bg); }
                else c.Text(cue, 6, y, cc);
            }
            else if (!two) c.Text((t.Range / 1000f).ToString("0.0", CultureInfo.InvariantCulture) + "KM", 6, y, White);
            if (t.Tof >= 0f)
            {
                string tof = "TOF " + Mathf.RoundToInt(t.Tof);
                c.Text(tof, (c.W - TextWidth(tof)) / 2 + 6, y, White);
            }
            float az = t.OffAz;
            string off = "OFF " + Mathf.RoundToInt(Math.Abs(az)) + (Math.Abs(az) < 0.5f ? "" : az < 0 ? "L" : "R");
            c.Text(off, c.W - 6 - TextWidth(off), y, Math.Abs(az) > 30f ? Amber : Cyan);
        }

        internal sealed class UfcpInfo
        {
            public TargetInfo Target;
            public float FuelKg, FuelLevel, Time;
            public bool Armed, Caution, GearWarn, Blink;
        }

        internal sealed class DwpItem
        {
            public string Text; public bool On, Red, Info;
            public DwpItem(string text, bool on, bool red, bool info = false) { Text = text; On = on; Red = red; Info = info; }
        }

        internal sealed class DwpInfo
        {
            public readonly System.Collections.Generic.List<DwpItem> Items = new System.Collections.Generic.List<DwpItem>();
            public bool Blink;
        }

        public static void Dwp(MfdCanvas c, DwpInfo w)
        {
            c.Clear(new Color32(4, 5, 6, 255));
            int W = c.W, H = c.H;
            var red = new Color32(255, 60, 40, 255);
            const int mx = 6, my = 6;
            int rows = 8, rowH = (H - 2 * my + 4) / rows, colW = (W - 2 * mx + 6) / 2;
            int x0 = (W - (2 * colW - 6)) / 2, y0 = (H - (rows * rowH - 4)) / 2;
            var unlit = new Color32(120, 22, 16, 255);
            var cell = new Color32(30, 6, 5, 255);
            for (int k = 0; k < rows * 2; k++)
            {
                int ux = x0 + (k / rows) * colW, uy = y0 + (k % rows) * rowH;
                c.Fill(ux, uy, colW - 6, rowH - 4, cell);
                int sw = (colW - 14) / 3;
                for (int seg = 0; seg < 3; seg++)
                    c.Fill(ux + 4 + seg * sw, uy + 4, sw - 4, rowH - 12, unlit);
            }
            int i = 0;
            foreach (var it in w.Items)
            {
                if (!it.On) continue;
                if (i >= rows * 2) break;
                int x = x0 + (i / rows) * colW, y = y0 + (i % rows) * rowH;
                Color32 col = it.Red ? red : it.Info ? new Color32(90, 255, 120, 255) : Amber;
                if (it.Red && !w.Blink) col = new Color32((byte)(col.r / 3), (byte)(col.g / 3), (byte)(col.b / 3), 255);
                c.Fill(x, y, colW - 6, rowH - 4, new Color32(6, 6, 6, 255));
                c.Box(x, y, colW - 6, rowH - 4, col, 1);
                string s = it.Text.Length * 10 > colW - 12 ? it.Text.Substring(0, Math.Max(1, (colW - 12) / 10)) : it.Text;
                c.Text(s, x + 4, y + (rowH - 4 - 16) / 2, col);
                i++;
            }
        }

        static readonly Color32 UGreen = new Color32(90, 255, 120, 255);

        public static void Ufcp(MfdCanvas c, UfcpInfo u)
        {
            c.Clear(Bg);
            int W = c.W, H = c.H;
            var t = u.Target ?? new TargetInfo();
            int bw = (W - 16) / 3;
            Lamp(c, 4, 4, bw, "CAUT", u.Caution && u.Blink, Amber);
            Lamp(c, 8 + bw, 4, bw, "MSL", t.MissileWarn && u.Blink, Red);
            Lamp(c, 12 + 2 * bw, 4, bw, "LOCK", t.RadarLock, Amber);
            int y = 30, step = Math.Max(18, (H - 34) / 5);
            int s = (int)u.Time;
            c.Text("UHF 243.00", 8, y, UGreen); y += step;
            c.Text(string.Format("TIME {0:00}:{1:00}:{2:00}", s / 3600 % 24, s / 60 % 60, s % 60), 8, y, UGreen); y += step;
            c.Text(u.Armed ? "MA ARM" : "MA SAFE", 8, y, u.Armed ? UGreen : Grey); y += step;
            c.Text("FUEL " + Mathf.RoundToInt(u.FuelKg), 8, y, u.FuelLevel < 0.15f ? Amber : UGreen); y += step;
            string w = string.IsNullOrEmpty(t.Weapon) ? "" : t.Weapon;
            if (w.Length > (W - 16) / 10) w = w.Substring(0, (W - 16) / 10);
            if (y + 16 <= H) c.Text(w, 8, y, Cyan);
            if (u.GearWarn && u.Blink) { c.Fill(W - 70, H - 22, 66, 18, Red); c.Text("GEAR", W - 62, H - 21, Bg); }
        }

        internal sealed class MdefInfo
        {
            public float PosX, PosZ, Heading;
            public string From, Text;
            public float Age;
            public bool Blink;
        }

        static readonly Color32 LcdBg = new Color32(58, 92, 172, 255), LcdInk = new Color32(228, 242, 255, 255), LcdDim = new Color32(126, 160, 226, 255);

        static List<string> Wrap(string s, int width)
        {
            var lines = new List<string>();
            foreach (var word0 in s.Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries))
            {
                string word = word0;
                while (word.Length > width) { lines.Add(word.Substring(0, width)); word = word.Substring(width); }
                if (lines.Count > 0 && lines[lines.Count - 1].Length + 1 + word.Length <= width) lines[lines.Count - 1] += " " + word;
                else lines.Add(word);
            }
            return lines;
        }

        public static void Mdef(MfdCanvas c, MdefInfo m)
        {
            c.Clear(LcdBg);
            int W = c.W, H = c.H, cols = Math.Max(6, (W - 6) / 10);
            int rows = Math.Max(2, (H - 4) / 17), step = (H - 4) / rows;
            int x0 = (W - cols * 10) / 2, y0 = 2 + (step - 16) / 2;
            if (m.Text == null)
            {
                double lat = 53.0 + m.PosZ / 111200.0, lon = -0.5 + m.PosX / 66900.0;
                Func<double, char, char, int, string> dm = (v, pos, neg, deg) =>
                {
                    char h = v >= 0 ? pos : neg; v = Math.Abs(v);
                    int d = (int)v; double mn = (v - d) * 60.0; if (mn >= 59.95) { mn = 0; d++; }
                    return h + d.ToString(deg == 3 ? "000" : "00") + " " + mn.ToString("00.0", System.Globalization.CultureInfo.InvariantCulture);
                };
                string[] l = { "WPT 01", dm(lat, 'N', 'S', 2), dm(lon, 'E', 'W', 3), "HDG " + (((int)Math.Round(m.Heading)) % 360).ToString("000") };
                int n = Math.Min(rows, l.Length);
                int top = 2 + (H - 4 - n * step) / 2 + (step - 16) / 2;
                for (int i = 0; i < n; i++) c.Text(l[i], x0, top + i * step, LcdInk);
                return;
            }
            string from = string.IsNullOrEmpty(m.From) ? "MSG" : m.From;
            if (from.Length > cols) from = from.Substring(0, cols);
            c.Fill(0, 0, W, step + 1, LcdInk);
            c.Text(from, x0, y0, LcdBg);
            var lines = Wrap(m.Text, cols);
            int per = rows - 1, pages = Math.Max(1, (lines.Count + per - 1) / per);
            int page = pages > 1 ? Math.Min(pages - 1, (int)(m.Age / 4f)) % pages : 0;
            for (int i = 0; i < per && page * per + i < lines.Count; i++)
                c.Text(lines[page * per + i], x0, y0 + (i + 1) * step, LcdInk);
            if (pages > 1) for (int i = 0; i < pages; i++) c.Fill(W - 5 - (pages - 1 - i) * 5, H - 4, 3, 2, i == page ? LcdInk : LcdDim);
        }

        static void Lamp(MfdCanvas c, int x, int y, int w, string label, bool on, Color32 col)
        {
            if (on) { c.Fill(x, y, w, 20, col); c.Text(label, x + (w - label.Length * 10) / 2, y + 2, Bg); }
            else { c.Box(x, y, w, 20, Dim, 1); c.Text(label, x + (w - label.Length * 10) / 2, y + 2, Dim); }
        }

        public static void Sadi(MfdCanvas c, FlightInfo f)
        {
            c.Clear(new Color32(10, 10, 12, 255));
            int W = c.W, H = c.H;
            float cx = W * 0.5f, cy = H * 0.5f, R = Math.Min(W, H) * 0.42f;
            float k = R / 40f, rr = f.Roll * Mathf.Deg2Rad, sr = Mathf.Sin(rr), cr = Mathf.Cos(rr);
            var sky = new Color32(70, 150, 225, 255); var gnd = new Color32(140, 90, 45, 255);
            for (int y = 0; y < H; y++)
                for (int x = 0; x < W; x++)
                {
                    float dx = x - cx, dy = y - cy;
                    if (dx * dx + dy * dy > R * R) continue;
                    float up = -dx * sr - dy * cr;
                    c.Set(x, y, up > -f.Pitch * k ? sky : gnd);
                }
            for (int a = -30; a <= 30; a += 10)
            {
                float off = (a - f.Pitch) * k;
                if (Math.Abs(off) > R * 0.85f) continue;
                float px = cx - sr * off, py = cy - cr * off, half = a == 0 ? R : (a % 20 == 0 ? R * 0.35f : R * 0.2f);
                c.Line(px - cr * half, py + sr * half, px + cr * half, py - sr * half, White, a == 0 ? 2 : 1);
            }
            c.Circle(cx, cy, R, Grey);
            foreach (int a in new[] { -60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60 })
            {
                float ang = a * Mathf.Deg2Rad;
                float sx = Mathf.Sin(ang), sy = -Mathf.Cos(ang);
                float r0 = R + 2, r1 = R + (a % 30 == 0 ? 10 : 6);
                c.Line(cx + sx * r0, cy + sy * r0, cx + sx * r1, cy + sy * r1, White, 1);
            }
            float pa = -rr; float psx = Mathf.Sin(pa), psy = -Mathf.Cos(pa);
            c.Line(cx + psx * (R - 10), cy + psy * (R - 10), cx + psx * (R - 1), cy + psy * (R - 1), Amber, 3);
            c.Line(cx - R * 0.55f, cy, cx - R * 0.18f, cy, Amber, 3); c.Line(cx + R * 0.18f, cy, cx + R * 0.55f, cy, Amber, 3);
            c.Fill((int)cx - 2, (int)cy - 2, 5, 5, Amber);
        }
    }
}
