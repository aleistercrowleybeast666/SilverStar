package cn.silverstar.gshc;
import android.content.Context;
import android.graphics.*;
import android.view.View;
import java.util.*;

public final class PlotView extends View {
    private final int channel;
    private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path=new Path();
    private static final String[] TITLES={"E · 速度","N · 速度","U · 速度","E · 位置","N · 位置","U · 位置"};
    private java.util.List<double[]> points=Collections.emptyList();
    public PlotView(Context context){this(context,0);}
    public PlotView(Context context,int channel){super(context);this.channel=channel;setContentDescription(title()+"，最近300个样本。点击查看放大曲线");setFocusable(true);setBackgroundColor(Color.WHITE);}
    private String title(){return TITLES[channel];}
    public void update(java.util.List<double[]> p){points=p;invalidate();}
    @Override protected void onDraw(Canvas canvas){
        super.onDraw(canvas);float d=getResources().getDisplayMetrics().density,sp=getResources().getDisplayMetrics().scaledDensity;
        float left=10*d,right=getWidth()-10*d,top=74*sp,bottom=getHeight()-30*sp;
        paint.setColor(Color.rgb(30,49,61));paint.setTextSize(12*sp);canvas.drawText(title(),left,20*sp,paint);
        paint.setColor(Color.rgb(213,225,231));paint.setStrokeWidth(d);for(int i=0;i<4;i++){float y=top+(bottom-top)*i/3;canvas.drawLine(left,y,right,y,paint);}
        if(points.isEmpty()){paint.setColor(Color.GRAY);canvas.drawText("等待遥测",left,48*sp,paint);return;}
        double min=0,max=0;for(double[] p:points){if(Double.isFinite(p[channel])){min=Math.min(min,p[channel]);max=Math.max(max,p[channel]);}}
        if(max-min<0.01)max=min+1;
        paint.setColor(Color.rgb(35,104,138));canvas.drawText(String.format(Locale.ROOT,"%.3g",points.get(points.size()-1)[channel]),left,44*sp,paint);
        paint.setTextSize(10*sp);canvas.drawText((channel<3?"m/s":"m")+String.format(Locale.ROOT," [%.2g, %.2g]",min,max),left,61*sp,paint);
        path.reset();boolean started=false;
        for(int i=0;i<points.size();i++){
            double value=points.get(i)[channel];if(!Double.isFinite(value)){started=false;continue;}
            float x=left+(right-left)*i/Math.max(1,points.size()-1),y=bottom-(float)((value-min)/(max-min))*(bottom-top);
            if(!started){path.moveTo(x,y);started=true;}else path.lineTo(x,y);
        }
        paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(2*d);canvas.drawPath(path,paint);paint.setStyle(Paint.Style.FILL);
        paint.setColor(Color.GRAY);canvas.drawText("旧 ← 样本 → 新",left,getHeight()-10*sp,paint);
    }
}
