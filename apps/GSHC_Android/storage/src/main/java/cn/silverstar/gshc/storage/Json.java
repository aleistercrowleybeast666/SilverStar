package cn.silverstar.gshc.storage;

import java.util.Map;

/** Small encoder only. Untrusted JSON parsing stays at the platform boundary. */
public final class Json {
    private Json() {}
    public static String encode(Object value) {
        if (value == null) return "null";
        if (value instanceof String) return quote((String) value);
        if (value instanceof Boolean) return value.toString();
        if (value instanceof Number) {
            double d = ((Number) value).doubleValue();
            return Double.isFinite(d) ? value.toString() : "null";
        }
        StringBuilder out = new StringBuilder();
        if (value instanceof Map<?, ?>) {
            out.append('{');
            for (Map.Entry<?, ?> e : ((Map<?, ?>) value).entrySet()) {
                if (out.length() > 1) out.append(',');
                out.append(quote(e.getKey().toString())).append(':').append(encode(e.getValue()));
            }
            return out.append('}').toString();
        }
        if (value instanceof Iterable<?>) {
            out.append('[');
            for (Object v : (Iterable<?>) value) {
                if (out.length() > 1) out.append(',');
                out.append(encode(v));
            }
            return out.append(']').toString();
        }
        throw new IllegalArgumentException("Unsupported JSON value " + value.getClass());
    }
    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"': out.append("\\\""); break;
                case '\\': out.append("\\\\"); break;
                case '\n': out.append("\\n"); break;
                case '\r': out.append("\\r"); break;
                case '\t': out.append("\\t"); break;
                default:
                    if (c < 32) out.append(String.format("\\u%04x", (int)c));
                    else out.append(c);
            }
        }
        return out.append('"').toString();
    }
}
