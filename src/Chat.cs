using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.RegularExpressions;
using BepInEx.Logging;
using HarmonyLib;
using UnityEngine;

namespace TyphoonMod
{
    internal static class ChatFeed
    {
        internal sealed class Msg { public string From, Text; public float At; }
        internal static readonly List<Msg> Messages = new List<Msg>();
        internal static bool Enabled = true;
        internal static float ShowSeconds = 14f;
        static string _kind;
        static readonly Regex Tags = new Regex("<[^>]*>", RegexOptions.Compiled);

        internal static void Install(Harmony h, ManualLogSource log)
        {
            try
            {
                var cm = AccessTools.TypeByName("NuclearOption.Chat.ChatManager");
                var ui = AccessTools.TypeByName("GameplayUI");
                if (cm == null || ui == null) { log.LogInfo("Chat display: the game's chat was not found; the keypad display shows the waypoint only."); return; }
                int n = 0;
                foreach (var m in AccessTools.GetDeclaredMethods(cm))
                {
                    bool chat = m.Name.StartsWith("UserCode_TargetReceiveMessage"), srv = m.Name.StartsWith("UserCode_RpcServerMessage") || m.Name.StartsWith("UserCode_RpcTargetServerMessage");
                    if (!chat && !srv) continue;
                    h.Patch(m, prefix: new HarmonyMethod(typeof(ChatFeed), chat ? nameof(BeginChat) : nameof(BeginServer)),
                               finalizer: new HarmonyMethod(typeof(ChatFeed), nameof(End)));
                    n++;
                }
                int g = 0;
                foreach (var m in AccessTools.GetDeclaredMethods(ui))
                {
                    var ps = m.Name == "GameMessage" ? m.GetParameters() : null;
                    if (ps == null || ps.Length == 0 || ps[0].ParameterType != typeof(string)) continue;
                    h.Patch(m, prefix: new HarmonyMethod(typeof(ChatFeed), nameof(OnGameMessage)));
                    g++;
                }
                log.LogInfo($"Chat display: listening to {n} chat method(s) through {g} message method(s).");
            }
            catch (Exception e) { log.LogWarning("Chat display: " + e.Message); }
        }

        static void BeginChat() { _kind = "chat"; }
        static void BeginServer() { _kind = "server"; }
        static void End() { _kind = null; }

        static void OnGameMessage(string __0)
        {
            string kind = _kind;
            if (kind == null || !Enabled || string.IsNullOrEmpty(__0)) return;
            _kind = null;
            try
            {
                string s = Tags.Replace(__0, "").Trim();
                string from = kind == "server" ? "SERVER" : "", text = s;
                if (kind == "chat")
                {
                    int i = s.IndexOf(": ", StringComparison.Ordinal);
                    if (i < 0) i = s.IndexOf(':');
                    if (i > 0) { from = s.Substring(0, i).Trim(); text = s.Substring(Math.Min(s.Length, i + 1)).Trim(); }
                    if (from.StartsWith("(ally)", StringComparison.OrdinalIgnoreCase)) from = from.Substring(6).Trim();
                }
                if (text.Length == 0) return;
                Messages.Add(new Msg { From = Clean(from), Text = Clean(text), At = Time.unscaledTime });
                if (Messages.Count > 12) Messages.RemoveAt(0);
            }
            catch { }
        }

        static string Clean(string s)
        {
            var sb = new System.Text.StringBuilder(s.Length);
            foreach (char c0 in s.ToUpperInvariant())
            {
                char c = c0;
                if (c == '\n' || c == '\r' || c == '\t') c = ' ';
                if (c < 32 || c > 95) c = c == '{' ? '(' : c == '}' ? ')' : c == '|' ? '/' : c == '~' ? '-' : c == '`' ? '\'' : '?';
                sb.Append(c);
            }
            return sb.ToString();
        }

        internal static Msg Current(int charsPerPage, out float age)
        {
            age = 0f;
            if (Messages.Count == 0) return null;
            var m = Messages[Messages.Count - 1];
            age = Time.unscaledTime - m.At;
            int pages = Mathf.Max(1, Mathf.CeilToInt(m.Text.Length / (float)Mathf.Max(8, charsPerPage)));
            return age <= Mathf.Max(ShowSeconds, pages * 4f + 2f) ? m : null;
        }

        internal static bool Recent { get { float a; return Current(48, out a) != null; } }
    }
}
