#!/usr/bin/env python3
import argparse
from labprism.artifacts import receive_media
p = argparse.ArgumentParser(description='Receive a verified AnnotationWorkbench demo export')
p.add_argument('producer_directory'); p.add_argument('destination')
a = p.parse_args()
print(receive_media(a.producer_directory, a.destination)['source_id'])
