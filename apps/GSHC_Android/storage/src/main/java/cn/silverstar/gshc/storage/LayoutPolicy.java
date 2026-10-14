package cn.silverstar.gshc.storage;

/** Pure window policy shared by native UI and CPU layout tests. Indices V_E,V_N,V_U,P_E,P_N,P_U. */
public final class LayoutPolicy {
    private LayoutPolicy() {}
    public static int columns(float usableWidthDp){return usableWidthDp>=840?3:2;}
    public static int[] order(float usableWidthDp){return columns(usableWidthDp)==2?new int[]{0,3,1,4,2,5}:new int[]{0,1,2,3,4,5};}
    public static int chartHeight(float fontScale){return Math.round(220*Math.max(1,fontScale));}
    public static boolean splitPreflight(float widthDp,float heightDp){return widthDp>=840&&heightDp>=480;}
}
