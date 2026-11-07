// SYNTHETIC TEST PROCESS. This is not OpenAI Codex or an AI harness.
// The executable basename exercises Herdr 0.9.5's fixed process-name selector.
// No network, credentials, subprocesses or provider inference are used.
using System;
using System.IO;
using System.Threading;
public static class Fixture {
    public static void Main(string[] args) {
        if (args.Length != 1) return;
        Console.WriteLine("SYNTHETIC Nexus PR09 observation identity fixture; no AI/provider.");
        while (!File.Exists(args[0])) Thread.Sleep(100);
    }
}
