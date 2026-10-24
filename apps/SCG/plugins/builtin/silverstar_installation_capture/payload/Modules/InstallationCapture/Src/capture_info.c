#include "capture_internal.h"
#include <stddef.h>
#include "project_installation_capture.h"

/* A generated target integration must supply its reviewed immutable profile
 * mapping. This candidate has test endpoints and generated physical
 * endpoint labels only; no chip UID or measurement timestamp is invented. */
static const char * const s_driver[4]={"mock.imu","mock.mag",INSTALLATION_CAPTURE_IMU_DRIVER,INSTALLATION_CAPTURE_MAG_DRIVER};
static const char * const s_model[4]={"fixture","fixture",INSTALLATION_CAPTURE_IMU_MODEL,INSTALLATION_CAPTURE_MAG_MODEL};

void CaptureSink_Byte(CaptureSink *sink, uint8_t value)
{
    if (sink->position>=8192U) {sink->failed=1U;return;}
    if (sink->hash!=NULL) {CaptureSha_Byte(sink->hash,value);}
    if ((sink->output!=NULL)&&(sink->position>=sink->from)&&(sink->length<sink->capacity)) {
        sink->output[sink->length++]=value;
    }
    sink->position++;
}

static void Json_Text(CaptureSink *s, const char *value)
{
    uint16_t i;
    for (i=0U;i<512U;i++) {
        if (value[i]=='\0') {return;}
        CaptureSink_Byte(s,(uint8_t)value[i]);
    }
    s->failed=1U;
}

static void Json_Uint(CaptureSink *s, uint32_t value)
{
    uint32_t divisor=1000000000U;
    uint8_t i,started=0U;
    for (i=0U;i<10U;i++) {
        uint32_t digit=value/divisor;
        if ((digit!=0U)||(started!=0U)||(divisor==1U)) {
            CaptureSink_Byte(s,(uint8_t)('0'+digit));started=1U;
        }
        value%=divisor;divisor=(divisor>1U)?divisor/10U:1U;
    }
}

static void Json_String(CaptureSink *s, const char *value)
{CaptureSink_Byte(s,'"');Json_Text(s,value);CaptureSink_Byte(s,'"');}

static void Json_Hex(CaptureSink *s, const uint8_t *value, uint8_t count)
{
    static const char alphabet[]="0123456789abcdef";
    uint8_t i;
    CaptureSink_Byte(s,'"');
    for (i=0U;i<count;i++) {CaptureSink_Byte(s,(uint8_t)alphabet[value[i]>>4]);CaptureSink_Byte(s,(uint8_t)alphabet[value[i]&15U]);}
    CaptureSink_Byte(s,'"');
}

static void Json_Config(CaptureSink *s, uint32_t value)
{
    static const char alphabet[]="0123456789abcdef";
    uint8_t i;
    Json_Text(s,"\"cfg-");
    for (i=0U;i<8U;i++) {CaptureSink_Byte(s,(uint8_t)alphabet[(value>>(28U-4U*i))&15U]);}
    CaptureSink_Byte(s,'"');
}

static void Json_Float(CaptureSink *s, double value)
{
    char text[32];uint16_t size=0U,i;
    if (CaptureNumber_Write(value,text,&size)!=InstallationCaptureResult_Ok) {s->failed=1U;return;}
    for (i=0U;i<size;i++) {CaptureSink_Byte(s,(uint8_t)text[i]);}
}

static void Json_Vector(CaptureSink *s, const double *value)
{
    uint8_t i;CaptureSink_Byte(s,'[');
    for (i=0U;i<3U;i++) {if (i!=0U) {CaptureSink_Byte(s,',');}Json_Float(s,value[i]);}
    CaptureSink_Byte(s,']');
}

static void Json_Matrix(CaptureSink *s, const double value[9])
{
    uint8_t i;CaptureSink_Byte(s,'[');
    for (i=0U;i<3U;i++) {if (i!=0U) {CaptureSink_Byte(s,',');}Json_Vector(s,&value[i*3U]);}
    CaptureSink_Byte(s,']');
}

static void Json_Boot(CaptureSink *s, const CaptureFrozen *f)
{
    if (f->snapshot.boot_known!=0U) {Json_Hex(s,f->snapshot.boot,16U);}
    else {Json_String(s,"UNKNOWN");}
}

static void Json_Identity(CaptureSink *s, const InstallationCaptureSource *source)
{
    Json_Text(s,"{\"board\":");Json_String(s,source->profile<2U?"SYNTHETIC":INSTALLATION_CAPTURE_BOARD);
    Json_Text(s,",\"configuration\":");Json_Config(s,source->configuration);
    Json_Text(s,",\"descriptor\":");Json_Uint(s,source->descriptor);
    Json_Text(s,",\"driver\":");Json_String(s,s_driver[source->profile]);
    Json_Text(s,",\"instance\":");Json_Uint(s,source->instance);
    Json_Text(s,",\"model\":");Json_String(s,s_model[source->profile]);
    Json_Text(s,",\"physical\":");Json_Uint(s,source->physical);
    Json_Text(s,",\"raw_frame\":");Json_String(s,(source->profile&1U)!=0U?"M0":"A0");CaptureSink_Byte(s,'}');
}

static void Json_Intrinsic(CaptureSink *s, const CaptureFrozen *f, uint8_t role)
{
    uint8_t available=(uint8_t)(f->snapshot.sources[role].intrinsic_generation!=0U);
    Json_Text(s,"{\"bias\":");
    if(available!=0U){Json_Vector(s,role==0U?f->snapshot.accel_bias:f->snapshot.mag_bias);}else{Json_Text(s,"null");}
    Json_Text(s,",\"calibration_id\":");Json_String(s,f->snapshot.intrinsic_id[role]);
    Json_Text(s,",\"gauge\":\"SPD_COLUMN\",\"generation\":");Json_Uint(s,f->snapshot.sources[role].intrinsic_generation);
    Json_Text(s,",\"identity\":");Json_Identity(s,&f->snapshot.sources[role]);
    Json_Text(s,",\"matrix\":");
    if(available!=0U){Json_Matrix(s,role==0U?f->snapshot.accel_matrix:f->snapshot.mag_matrix);}else{Json_Text(s,"null");}
    Json_Text(s,",\"output_frame\":");Json_String(s,role==0U?"A":"M");
    Json_Text(s,",\"unit\":");Json_String(s,role==0U?"m/s2":"uT");CaptureSink_Byte(s,'}');
}

static void Json_Axis(CaptureSink *s, const int8_t axis[3])
{
    uint8_t i;CaptureSink_Byte(s,'[');
    for (i=0U;i<3U;i++) {
        int value=axis[i];if (i!=0U) {CaptureSink_Byte(s,',');}
        if (value<0) {CaptureSink_Byte(s,'-');value=-value;}
        Json_Uint(s,(uint32_t)value);
    }
    CaptureSink_Byte(s,']');
}

static void Json_Source(CaptureSink *s, const CaptureFrozen *f, uint8_t role)
{
    const InstallationCaptureSource *source=&f->snapshot.sources[role];
    Json_Text(s,"{\"axis_mapping_applied\":");Json_Axis(s,source->axis_map);
    Json_Text(s,",\"boot\":");Json_Boot(s,f);
    Json_Text(s,",\"clock\":\"BOOT_MONOTONIC\",\"clock_provenance\":");
    Json_String(s,source->profile<2U?"SYNTHETIC_SHARED_CLOCK":"LOCAL_DECODE_NOT_MEASUREMENT");
    Json_Text(s,",\"correction_layer\":\"PROVIDER_PHYSICAL_BEFORE_SOFTWARE_CORRECTION\",\"epoch\":");Json_Uint(s,source->epoch);
    Json_Text(s,",\"frame_provenance\":\"DECLARED_AXIS_MAPPING\",\"handedness\":\"RIGHT\",\"identity\":");Json_Identity(s,source);
    Json_Text(s,",\"intrinsic_generation\":");Json_Uint(s,source->intrinsic_generation);
    Json_Text(s,",\"intrinsic_id\":");Json_String(s,f->snapshot.intrinsic_id[role]);
    Json_Text(s,",\"provider_calibration\":\"UNKNOWN\",\"role\":");Json_String(s,role==0U?"IMU":"MAG");
    Json_Text(s,",\"sample_time_bits\":64,\"sequence_stride\":");Json_Uint(s,source->stride);
    Json_Text(s,",\"timestamp_saturates\":false,\"units\":");
    Json_Text(s,role==0U?"[\"m/s2\",\"rad/s\"]}":"[\"uT\"]}");
}

static void Json_Policy(CaptureSink *s, const CaptureFrozen *f)
{
    Json_Text(s,"{\"archive_capacity\":8192,\"max_skew_us\":");Json_Uint(s,f->snapshot.maximum_skew_us);
    Json_Text(s,",\"max_uncertainty_us\":");Json_Uint(s,f->snapshot.maximum_uncertainty_us);
    Json_Text(s,",\"min_pairs\":3,\"pair_capacity\":4096,\"source_capacity\":8,\"source_timeout_us\":");Json_Uint(s,f->snapshot.source_timeout_us);
    Json_Text(s,",\"window_timeout_us\":");Json_Uint(s,f->snapshot.face_timeout_us);CaptureSink_Byte(s,'}');
}

static void Json_TimeSource(CaptureSink *s, const InstallationCaptureSource *source)
{
    uint8_t known=(uint8_t)((source->profile<2U)&&(source->time_basis==2U)&&(source->proof_flags==7U));
    Json_Text(s,"{\"epoch_provenance\":");Json_String(s,known!=0U?"TEST_FIXTURE":"UNKNOWN");
    Json_Text(s,",\"hardware_identity\":null,\"hardware_identity_provenance\":\"UNKNOWN\",\"identity_scope\":");
    Json_String(s,source->profile<2U?"SYNTHETIC_ENDPOINT":"DECLARED_ENDPOINT");
    Json_Text(s,",\"measurement_uncertainty_bound_us\":");
    if (known!=0U) {Json_Uint(s,source->uncertainty_us);} else {Json_Text(s,"null");}
    Json_Text(s,",\"native_sequence_provenance\":");Json_String(s,known!=0U?"TEST_FIXTURE":"UNKNOWN");
    Json_Text(s,",\"sample_time_basis\":");
    Json_String(s,known!=0U?"SYNTHETIC_MEASUREMENT":source->time_basis==1U?"TARGET_RECEIVE_DECODE_PROXY":"UNKNOWN");
    Json_Text(s,",\"sample_time_provenance\":");
    Json_String(s,known!=0U?"TEST_FIXTURE":source->time_basis==1U?"JY901B_LOCAL_DECODE":"UNKNOWN");CaptureSink_Byte(s,'}');
}

static void Json_Provenance(CaptureSink *s, const CaptureFrozen *f)
{
    Json_Text(s,"{\"native_health_timeout_us\":");Json_Uint(s,f->snapshot.native_health_timeout_us);
    Json_Text(s,",\"selected_interval_max_us\":");Json_Uint(s,f->snapshot.selected_interval_max_us);
    Json_Text(s,",\"selection\":{\"kind\":\"FIXED_NATIVE_SEQUENCE_STRIDE\",\"native_rate_unchanged\":true,\"nominal_output_millihz\":");Json_Uint(s,f->snapshot.nominal_output_millihz);
    Json_Text(s,",\"phase\":{\"IMU\":");Json_Uint(s,f->snapshot.sources[0].phase);
    Json_Text(s,",\"MAG\":");Json_Uint(s,f->snapshot.sources[1].phase);
    Json_Text(s,"},\"value_dependent\":false},\"sources\":{\"IMU\":");Json_TimeSource(s,&f->snapshot.sources[0]);
    Json_Text(s,",\"MAG\":");Json_TimeSource(s,&f->snapshot.sources[1]);Json_Text(s,"}}");
}

static void Json_Convention(CaptureSink *s, const CaptureFrozen *f)
{
    Json_Text(s,"{\"R_GA\":");
    if (f->snapshot.R_GA_known!=0U) {Json_Matrix(s,f->snapshot.R_GA);} else {Json_Text(s,"null");}
    Json_Text(s,",\"accel_frame\":\"A\",\"acceleration_kind\":\"STATIC_SPECIFIC_FORCE_UP\",\"evidence\":\"DECLARED_ONLY\",\"gyro_axis_evidence\":");
    Json_String(s,f->snapshot.R_GA_known!=0U?"CALLER_DECLARED_NOT_VERIFIED":"UNPROVEN");
    Json_Text(s,",\"gyro_frame\":\"G\",\"handedness\":\"RIGHT\",\"mag_frame\":\"M\",\"transformation\":\"COLUMN_M_TO_A\",\"units\":[\"m/s2\",\"rad/s\",\"uT\"]}");
}

void CaptureInfo_Output(CaptureSink *s, const CaptureFrozen *f, uint8_t include_binding)
{
    Json_Text(s,"{\"accel\":");Json_Intrinsic(s,f,0U);
    Json_Text(s,",\"base_generation\":");Json_Uint(s,f->snapshot.base_generation);
    if (include_binding!=0U) {Json_Text(s,",\"binding_digest\":");Json_Hex(s,f->binding,32U);}
    Json_Text(s,",\"boot\":");Json_Boot(s,f);
    Json_Text(s,",\"capture_policy\":");Json_Policy(s,f);
    Json_Text(s,",\"capture_provenance\":");Json_Provenance(s,f);
    Json_Text(s,",\"configuration_u32\":");Json_Uint(s,f->snapshot.configuration);
    Json_Text(s,",\"convention\":");Json_Convention(s,f);
    Json_Text(s,",\"face_plan\":{\"automatic\":true,\"holdout_pairs\":");Json_Uint(s,f->snapshot.holdout_pairs);
    Json_Text(s,",\"train_pairs\":");Json_Uint(s,f->snapshot.train_pairs);CaptureSink_Byte(s,'}');
    Json_Text(s,",\"mag\":");Json_Intrinsic(s,f,1U);
    Json_Text(s,",\"runtime_imu\":{\"bias_radps\":");
    if(f->snapshot.gyro_known!=0U){Json_Vector(s,f->snapshot.gyro_bias);}else{Json_Text(s,"null");}
    Json_Text(s,",\"generation\":");Json_Uint(s,f->snapshot.sources[0].intrinsic_generation);
    Json_Text(s,",\"mode\":");Json_Uint(s,f->snapshot.gyro_mode);
    Json_Text(s,",\"ready\":");Json_Text(s,f->snapshot.gyro_known!=0U?"true":"false");
    Json_Text(s,",\"scale\":");
    if(f->snapshot.gyro_known!=0U){Json_Vector(s,f->snapshot.gyro_scale);}else{Json_Text(s,"null");}
    Json_Text(s,"},\"sources\":{\"IMU\":");Json_Source(s,f,0U);
    Json_Text(s,",\"MAG\":");Json_Source(s,f,1U);Json_Text(s,"}}");
}
