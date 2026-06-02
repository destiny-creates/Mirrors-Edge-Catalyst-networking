import pefile, sys

try:
    pe = pefile.PE('/home/parrot/Downloads/ME/MirrorsEdgeCatalyst.exe', fast_load=False)
    pe.parse_data_directories()
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        dll = entry.dll.decode('utf-8', 'ignore')
        print(f'DLL: {dll}')
        for i in entry.imports:
            name = i.name.decode('utf-8', 'ignore') if i.name else f'ord_{i.ordinal}'
            print(f'  {name}')
except Exception as e:
    print('Error:', e)
