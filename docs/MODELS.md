# Models

1. **Primary detector – TrafficCamNet** (classes: car, person, bicycle, road_sign)
   NGC: https://catalog.ngc.nvidia.com/orgs/nvidia/teams/tao/models/trafficcamnet
   Put the model file (`resnet18_trafficcamnet_pruned.etlt`, or `.onnx` on DeepStream 7+),
   `trafficcamnet_int8.txt` (calibration) and `labels.txt` in `deepstream/models/trafficcamnet/`.
   DeepStream ships a reference config: `samples/configs/tao_pretrained_models/config_infer_primary_trafficcamnet.txt`.

2. **Secondary classifier – car colour** (DeepStream sample `Secondary_CarColor`, DS 5/6)
   Found in `/opt/nvidia/deepstream/deepstream/samples/models/Secondary_CarColor/`.
   Copy `resnet18.caffemodel`, `resnet18.prototxt`, `mean.ppm`, `labels.txt` to `deepstream/models/carcolor/`.
   DeepStream 7.x removed this sample: fine-tune a colour classifier (e.g. TAO ImageClassification),
   export ONNX, then edit `config/sgie_color_config.txt` (`onnx-file`, `labelfile-path`).
