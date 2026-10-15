// Trusted syntax inspection only. Candidate source is parsed, never compiled or executed.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

internal static class Program
{
    private static bool IsLiteralText(SyntaxToken token)
    {
        // Roslyn exposes expressions inside every interpolation as ordinary code tokens.
        // Literal text, including raw/verbatim/UTF8 strings, must not become API names.
        string kind = token.Kind().ToString();
        return kind.EndsWith("StringLiteralToken", StringComparison.Ordinal)
            || token.IsKind(SyntaxKind.CharacterLiteralToken)
            || token.IsKind(SyntaxKind.InterpolatedStringTextToken);
    }

    private static string NameText(NameSyntax name) =>
        string.Concat(name.DescendantTokens().Select(token => token.ValueText));

    public static int Main()
    {
        Console.InputEncoding = Encoding.UTF8;
        Console.OutputEncoding = new UTF8Encoding(false);
        string source = Console.In.ReadToEnd();
        // The Python boundary enforces the historical 180,000-code-point limit.
        // This independent UTF16 bound also prevents unbounded direct helper input.
        if (source.Length > 360000)
        {
            Console.Error.WriteLine("bounded C# required");
            return 2;
        }

        SyntaxTree tree = CSharpSyntaxTree.ParseText(source,
            new CSharpParseOptions(LanguageVersion.CSharp13, DocumentationMode.Parse));
        SyntaxNode root = tree.GetRoot();
        SyntaxToken[] tokens = root.DescendantTokens().Where(token => !IsLiteralText(token)).ToArray();
        var errors = tree.GetDiagnostics().Where(item => item.Severity == DiagnosticSeverity.Error)
            .Take(8).Select(item => new {
                id = item.Id,
                line = item.Location.GetLineSpan().StartLinePosition.Line + 1,
                column = item.Location.GetLineSpan().StartLinePosition.Character + 1
            }).ToArray();
        string[] identifiers = tokens.Where(token => token.IsKind(SyntaxKind.IdentifierToken)
                || SyntaxFacts.IsKeywordKind(token.Kind()))
            .Select(token => token.ValueText).Distinct().OrderBy(value => value, StringComparer.Ordinal).ToArray();

        // Work in Roslyn's own token model. No UTF16 offsets are sliced in Python.
        var qualified = new HashSet<string>(StringComparer.Ordinal);
        for (int i = 0; i < tokens.Length - 2; ++i)
        {
            if (tokens[i].ValueText != "System" || !tokens[i + 1].IsKind(SyntaxKind.DotToken))
                continue;
            var parts = new List<string> { "System" };
            int j = i;
            while (j + 2 < tokens.Length && tokens[j + 1].IsKind(SyntaxKind.DotToken)
                && tokens[j + 2].IsKind(SyntaxKind.IdentifierToken))
            {
                parts.Add(tokens[j + 2].ValueText);
                j += 2;
            }
            if (parts.Count > 1)
                qualified.Add(string.Join(".", parts));
        }

        UsingDirectiveSyntax[] usings = root.DescendantNodes().OfType<UsingDirectiveSyntax>().ToArray();
        string[] literals = root.DescendantNodes().OfType<LiteralExpressionSyntax>()
            .Where(node => node.Token.Value is string).Select(node => node.Token.ValueText)
            .Concat(root.DescendantNodes().OfType<InterpolatedStringTextSyntax>()
                .Select(node => node.TextToken.ValueText)).ToArray();
        bool hasMain = root.DescendantNodes().OfType<MethodDeclarationSyntax>().Any(method =>
            method.Identifier.ValueText == "Main" && method.TypeParameterList == null
            && method.ParameterList.Parameters.Count == 1
            && method.ParameterList.Parameters[0] is ParameterSyntax parameter
            && parameter.Modifiers.Count == 0 && parameter.AttributeLists.Count == 0
            && parameter.Type is ArrayTypeSyntax array && array.RankSpecifiers.Count == 1
            && array.RankSpecifiers[0].Rank == 1
            && array.ElementType is PredefinedTypeSyntax element
            && element.Keyword.IsKind(SyntaxKind.StringKeyword));

        Console.WriteLine(JsonSerializer.Serialize(new {
            schema = "picogk.am.policy-lexer@2",
            parse_errors = errors,
            identifiers_and_keywords = identifiers,
            non_ascii_executable = tokens.Any(token => token.Text.Any(character => character > 127)),
            escaped_identifier = tokens.Any(token => token.IsKind(SyntaxKind.IdentifierToken)
                && (token.Text.StartsWith("@", StringComparison.Ordinal) || token.Text.Contains('\\'))),
            preprocessor = root.ContainsDirectives,
            using_names = usings.Where(item => item.Name != null).Select(item => NameText(item.Name!)).ToArray(),
            aliases_or_global = usings.Any(item => item.Alias != null || !item.StaticKeyword.IsKind(SyntaxKind.None))
                || root.DescendantNodes().OfType<AliasQualifiedNameSyntax>().Any(),
            namespace_system = root.DescendantNodes().OfType<BaseNamespaceDeclarationSyntax>()
                .Any(item => item.Name.GetFirstToken().ValueText == "System"),
            system_qualified_names = qualified.OrderBy(value => value, StringComparer.Ordinal).ToArray(),
            string_values = literals,
            has_main = hasMain
        }));
        return 0;
    }
}
