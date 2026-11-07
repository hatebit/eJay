# Simulate exact mixplay flow
import pxd32d5
import pxdsink
import mixplay
import time

args = mixplay.build_parser().parse_args(['../../disk/MIX/TRANCE.MIX', '--res', '../../disk/RAVE'])
sink = mixplay.open_sink(args)  # uses sounddevice by default
return_code = mixplay.play(args, sink=sink, verbose=True)
print(return_code)
