import os
import subprocess

img_suffix = ['.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.dng', '.webp']

png_list = os.listdir('.')

text = ''
for i in png_list:
    if os.path.splitext(i)[1] in img_suffix:
        # <file alias="contacts.png">ico/contacts.png</file>
        text += f'<file alias="{i}">{i}</file>\n'

qrc_file = f"""
<!DOCTYPE RCC><RCC version="1.0">
<qresource>
{text}
</qresource>
</RCC>"""

print(qrc_file)

with open('resource.qrc', 'w') as f:
    f.write(qrc_file)

subprocess.run(['pyrcc5', 'resource.qrc', '-o', 'resource_rc.py'])
