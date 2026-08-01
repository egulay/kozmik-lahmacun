import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

export function formatDate(value?: string | null, locale = "tr-TR") {
	if (!value) return "—";
	return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(
		new Date(value),
	);
}

export function formatDuration(
	start?: string | null,
	end?: string | null,
	locale = "en-US",
) {
	if (!start) return "—";
	const milliseconds = Math.max(
		0,
		new Date(end ?? Date.now()).getTime() - new Date(start).getTime(),
	);
	const totalSeconds = Math.floor(milliseconds / 1_000);
	const formatUnit = (value: number, unit: "second" | "minute" | "hour") =>
		new Intl.NumberFormat(locale, {
			style: "unit",
			unit,
			unitDisplay: "short",
			maximumFractionDigits: 0,
		}).format(value);
	if (totalSeconds < 60) return formatUnit(totalSeconds, "second");
	const hours = Math.floor(totalSeconds / 3_600);
	const minutes = Math.floor((totalSeconds % 3_600) / 60);
	const seconds = totalSeconds % 60;
	return [
		hours ? formatUnit(hours, "hour") : "",
		hours || minutes ? formatUnit(minutes, "minute") : "",
		formatUnit(seconds, "second"),
	].filter(Boolean).join(" ");
}

export function humanizeField(value: string, locale = "en-US") {
	const replacements: Record<string, Record<string, string>> = {
		"en-US": { avg: "average", total: "total", count: "count", rate: "rate" },
		"tr-TR": { avg: "ortalama", total: "toplam", count: "sayı", rate: "oranı" },
	};
	const dictionary = replacements[locale] ?? replacements["en-US"];
	const words = value
		.replace(/^result\.(kpi|metric)\./, "")
		.split(/[_\s.]+/)
		.filter(Boolean)
		.map((word) => dictionary[word.toLowerCase()] ?? word.toLowerCase());
	if (!words.length) return value;
	const label = words.join(" ");
	return label.charAt(0).toLocaleUpperCase(locale) + label.slice(1);
}

export function formatDisplayValue(
	value: unknown,
	locale = "en-US",
	dataType?: string,
) {
	if (value === null || value === undefined || value === "") return "—";
	const numericString =
		typeof value === "string"
		&& /^-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(value.trim());
	const numericType = dataType
		? /^(BYTE|SHORT|INT|INTEGER|LONG|FLOAT|DOUBLE|DECIMAL|NUMBER)/i.test(dataType)
		: typeof value === "number" || numericString;
	const numericValue =
		typeof value === "number"
			? value
			: numericType && typeof value === "string" && value.trim() !== ""
				? Number(value)
				: Number.NaN;
	if (numericType && Number.isFinite(numericValue)) {
		return new Intl.NumberFormat(locale, {
			maximumFractionDigits: 4,
			minimumFractionDigits: 0,
		}).format(numericValue);
	}
	return String(value);
}

export function formatTemporalBucket(value: unknown, granularity?: string) {
	if (value === null || value === undefined || value === "") return "—";
	const text = String(value);
	const isoDate = /^(\d{4})-(\d{2})-(\d{2})/.exec(text);
	if (!isoDate) return text;
	const normalizedGranularity = granularity?.toUpperCase();
	if (normalizedGranularity === "YEAR") return isoDate[1];
	if (normalizedGranularity === "QUARTER") {
		return `${isoDate[1]}-Q${Math.floor((Number(isoDate[2]) - 1) / 3) + 1}`;
	}
	if (normalizedGranularity === "MONTH") return `${isoDate[1]}-${isoDate[2]}`;
	return `${isoDate[1]}-${isoDate[2]}-${isoDate[3]}`;
}

export function formatManagementSummary(value: string) {
	return value
		.replace(
			/^\s*(?:\*\*)?(?:decision summary|management summary|karar özeti|yönetici özeti)(?:\*\*)?\s*:?\s*/i,
			"",
		)
		.split(
			/\s*(?:\*\*)?(?:approved warnings|onaylı uyarılar)(?:\*\*)?\s*:?\s*/i,
			1,
		)[0]
		.replaceAll("**", "")
		.replaceAll("__", "")
		.trim();
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChild<T> = T extends { child?: any } ? Omit<T, "child"> : T;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChildren<T> = T extends { children?: any } ? Omit<T, "children"> : T;
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>;
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & { ref?: U | null };
