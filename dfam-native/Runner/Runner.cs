using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using PicoGK;

// Runs exactly one extracted corpus case: Runner NAMESPACE INPUT OUTPUT_DIR VOXEL_MM
// The case must expose public static void Run(Library, string, string) in
// NAMESPACE. Exit codes: 0 ok, 2 usage, 3 case threw, 4 entry point missing.
public static class CorpusRunner
{
    public static int Main(string[] args)
    {
        CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        if (args.Length != 4)
        {
            Console.Error.WriteLine("Usage: Runner NAMESPACE INPUT OUTPUT_DIR VOXEL_MM");
            return 2;
        }
        Type[] signature = { typeof(Library), typeof(string), typeof(string) };
        MethodInfo[] entries = Assembly.GetExecutingAssembly().GetTypes()
            .Where(t => t.Namespace == args[0])
            .Select(t => t.GetMethod("Run", BindingFlags.Public | BindingFlags.Static, null, signature, null))
            .Where(m => m != null)
            .ToArray();
        if (entries.Length != 1)
        {
            Console.Error.WriteLine($"Expected one Run(Library, string, string) in {args[0]}, found {entries.Length}");
            return 4;
        }
        Directory.CreateDirectory(args[2]);
        using Library lib = new(float.Parse(args[3], CultureInfo.InvariantCulture));
        try
        {
            entries[0].Invoke(null, new object[] { lib, args[1], args[2] });
        }
        catch (TargetInvocationException e)
        {
            Console.Error.WriteLine("CASE_EXCEPTION " + e.InnerException?.GetType().FullName + ": " + e.InnerException?.Message);
            return 3;
        }
        return 0;
    }
}
