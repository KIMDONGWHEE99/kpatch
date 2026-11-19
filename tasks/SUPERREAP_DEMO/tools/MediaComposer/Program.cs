using SkiaSharp;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length == 8 && args[0] == "compose")
        {
            Compose(args[1], args[2], args[3], args[4], args[5], args[6], args[7]);
            return 0;
        }
        if (args.Length < 2 || args[0] != "analyze")
        {
            Console.Error.WriteLine("사용법: analyze <png> [white|gold|alpha] [max-y]");
            Console.Error.WriteLine("또는: compose <설정 원본> <설정 생성> <배지 원본> <배지 생성> <슬롯 원본> <슬롯 생성> <출력 폴더>");
            return 1;
        }

        using var bitmap = SKBitmap.Decode(args[1]) ?? throw new InvalidDataException(args[1]);
        var mode = args.Length >= 3 ? args[2] : "white";
        var maxY = args.Length >= 4 ? Math.Min(int.Parse(args[3]), bitmap.Height) : bitmap.Height;
        var mask = new bool[bitmap.Width * maxY];
        for (var y = 0; y < maxY; y++)
        {
            for (var x = 0; x < bitmap.Width; x++)
            {
                var color = bitmap.GetPixel(x, y);
                mask[y * bitmap.Width + x] = mode switch
                {
                    "gold" => color.Red > 210 && color.Green > 120 && color.Blue < 105,
                    "alpha" => color.Alpha > 0,
                    _ => color.Red > 230 && color.Green > 230 && color.Blue > 230,
                };
            }
        }

        var visited = new bool[mask.Length];
        var components = new List<(int Count, int MinX, int MinY, int MaxX, int MaxY)>();
        var queue = new Queue<int>();
        for (var index = 0; index < mask.Length; index++)
        {
            if (!mask[index] || visited[index]) continue;
            visited[index] = true;
            queue.Enqueue(index);
            var count = 0;
            var minX = bitmap.Width;
            var minY = maxY;
            var maxX = -1;
            var maxFoundY = -1;
            while (queue.Count > 0)
            {
                var current = queue.Dequeue();
                var x = current % bitmap.Width;
                var y = current / bitmap.Width;
                count++;
                minX = Math.Min(minX, x);
                minY = Math.Min(minY, y);
                maxX = Math.Max(maxX, x);
                maxFoundY = Math.Max(maxFoundY, y);
                foreach (var (dx, dy) in new[] { (-1, 0), (1, 0), (0, -1), (0, 1) })
                {
                    var nx = x + dx;
                    var ny = y + dy;
                    if (nx < 0 || nx >= bitmap.Width || ny < 0 || ny >= maxY) continue;
                    var next = ny * bitmap.Width + nx;
                    if (!mask[next] || visited[next]) continue;
                    visited[next] = true;
                    queue.Enqueue(next);
                }
            }
            if (count >= 20) components.Add((count, minX, minY, maxX, maxFoundY));
        }

        Console.WriteLine($"image={bitmap.Width}x{bitmap.Height} mode={mode} maxY={maxY}");
        foreach (var item in components.OrderByDescending(item => item.Count).Take(100))
        {
            Console.WriteLine($"pixels={item.Count} box={item.MinX},{item.MinY},{item.MaxX},{item.MaxY}");
        }
        return 0;
    }

    private static void Compose(
        string settingsOriginal,
        string settingsGenerated,
        string badgeOriginal,
        string badgeGenerated,
        string slotOriginal,
        string slotGenerated,
        string outputDirectory)
    {
        Directory.CreateDirectory(outputDirectory);
        using var settings = SKBitmap.Decode(settingsOriginal) ?? throw new InvalidDataException(settingsOriginal);
        using var settingsGen = SKBitmap.Decode(settingsGenerated) ?? throw new InvalidDataException(settingsGenerated);
        EraseByHorizontalInterpolation(settings, new SKRectI(25, 6, 55, 19), 24, 56);
        using (var mask = ThresholdMask(settingsGen, new SKRectI(515, 120, 890, 295), "white"))
        {
            DrawMask(settings, mask, new SKRectI(27, 6, 53, 18), new SKColor(67, 91, 32, 210), SKColors.White);
        }
        Save(settings, Path.Combine(outputDirectory, "settings_ko.png"));

        using var badge = SKBitmap.Decode(badgeOriginal) ?? throw new InvalidDataException(badgeOriginal);
        using var badgeGen = SKBitmap.Decode(badgeGenerated) ?? throw new InvalidDataException(badgeGenerated);
        badge.Erase(SKColors.Transparent);
        var badgeRects = new[]
        {
            new SKRectI(120, 200, 320, 395),
            new SKRectI(619, 200, 819, 395),
            new SKRectI(1113, 200, 1313, 395),
            new SKRectI(1609, 200, 1809, 395),
        };
        var badgeColors = new[]
        {
            new SKColor(255, 255, 255, 255),
            new SKColor(245, 245, 245, 255),
            new SKColor(230, 230, 230, 255),
            new SKColor(245, 245, 245, 255),
        };
        for (var index = 0; index < badgeRects.Length; index++)
        {
            using var mask = ThresholdMask(badgeGen, badgeRects[index], "white");
            var x = index * 20 + 6;
            DrawMask(badge, mask, new SKRectI(x, 0, x + 8, 7), new SKColor(70, 70, 70, 180), badgeColors[index]);
        }
        Save(badge, Path.Combine(outputDirectory, "new_badge_ko.png"));

        using var slot = SKBitmap.Decode(slotOriginal) ?? throw new InvalidDataException(slotOriginal);
        using var slotGen = SKBitmap.Decode(slotGenerated) ?? throw new InvalidDataException(slotGenerated);
        var slotYOffset = slot.Height - 118;
        EraseByHorizontalInterpolation(slot, new SKRectI(10, 6 + slotYOffset, 94, 18 + slotYOffset), 5, 97);
        using (var mask = ThresholdMask(slotGen, new SKRectI(220, 45, 875, 195), "gold"))
        {
            DrawMask(
                slot,
                mask,
                new SKRectI(25, 6 + slotYOffset, 78, 17 + slotYOffset),
                new SKColor(84, 45, 25, 230),
                new SKColor(231, 180, 86, 255)
            );
        }
        Save(slot, Path.Combine(outputDirectory, "slot_ko.png"));

        Console.WriteLine($"settings={settings.Width}x{settings.Height}");
        Console.WriteLine($"badge={badge.Width}x{badge.Height}");
        Console.WriteLine($"slot={slot.Width}x{slot.Height}");
    }

    private static SKBitmap ThresholdMask(SKBitmap source, SKRectI crop, string mode)
    {
        var output = new SKBitmap(crop.Width, crop.Height, SKColorType.Bgra8888, SKAlphaType.Premul);
        output.Erase(SKColors.Transparent);
        for (var y = 0; y < crop.Height; y++)
        {
            for (var x = 0; x < crop.Width; x++)
            {
                var color = source.GetPixel(crop.Left + x, crop.Top + y);
                var hit = mode == "gold"
                    ? color.Red > 210 && color.Green > 120 && color.Blue < 105
                    : color.Red > 230 && color.Green > 230 && color.Blue > 230;
                if (hit) output.SetPixel(x, y, SKColors.White);
            }
        }
        return output;
    }

    private static void DrawMask(SKBitmap target, SKBitmap sourceMask, SKRectI destination, SKColor shadow, SKColor foreground)
    {
        using var scaled = new SKBitmap(destination.Width, destination.Height, SKColorType.Bgra8888, SKAlphaType.Premul);
        scaled.Erase(SKColors.Transparent);
        using (var canvas = new SKCanvas(scaled))
        using (var paint = new SKPaint { IsAntialias = false, FilterQuality = SKFilterQuality.None })
        {
            canvas.DrawBitmap(
                sourceMask,
                new SKRect(0, 0, sourceMask.Width, sourceMask.Height),
                new SKRect(0, 0, scaled.Width, scaled.Height),
                paint
            );
        }
        for (var y = 0; y < scaled.Height; y++)
        {
            for (var x = 0; x < scaled.Width; x++)
            {
                if (scaled.GetPixel(x, y).Alpha == 0) continue;
                var shadowX = destination.Left + x + 1;
                var shadowY = destination.Top + y + 1;
                if (shadowX < target.Width && shadowY < target.Height) target.SetPixel(shadowX, shadowY, shadow);
            }
        }
        for (var y = 0; y < scaled.Height; y++)
        {
            for (var x = 0; x < scaled.Width; x++)
            {
                if (scaled.GetPixel(x, y).Alpha == 0) continue;
                target.SetPixel(destination.Left + x, destination.Top + y, foreground);
            }
        }
    }

    private static void EraseByHorizontalInterpolation(SKBitmap bitmap, SKRectI region, int leftSampleX, int rightSampleX)
    {
        for (var y = region.Top; y < region.Bottom; y++)
        {
            var left = bitmap.GetPixel(leftSampleX, y);
            var right = bitmap.GetPixel(rightSampleX, y);
            for (var x = region.Left; x < region.Right; x++)
            {
                var amount = (float)(x - region.Left + 1) / (region.Width + 1);
                bitmap.SetPixel(
                    x,
                    y,
                    new SKColor(
                        (byte)(left.Red + (right.Red - left.Red) * amount),
                        (byte)(left.Green + (right.Green - left.Green) * amount),
                        (byte)(left.Blue + (right.Blue - left.Blue) * amount),
                        (byte)(left.Alpha + (right.Alpha - left.Alpha) * amount)
                    )
                );
            }
        }
    }

    private static void Save(SKBitmap bitmap, string path)
    {
        using var image = SKImage.FromBitmap(bitmap);
        using var data = image.Encode(SKEncodedImageFormat.Png, 100);
        using var stream = File.Open(path, FileMode.Create, FileAccess.Write, FileShare.None);
        data.SaveTo(stream);
    }
}
