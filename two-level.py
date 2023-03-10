import sst
from ariel_utils import parseAriel
import sys
import os

# Globals
NCORES            = 4
LATENCY           = '1000ps'
FREQ              = '2.0GHz'
COHERENCE         = 'MESI'
REPLACEMENT       = 'lru'
CACHE_LINE_BYTES  = '64'

# Utility method
def mklink(e1, e2):
      link = sst.Link('link___' + e1[0].getFullName() + '__' + e1[1] + '___' +
                                 e2[0].getFullName() + '__' + e2[1])
      link.connect(e1, e2)
      return link

def usage():
      print(f'Usage: sst [sst arguments] -- <config file>:<benchmark name>')
      print('The config file is generated by `generate.py`. The `benchmark name` should be a key in the dict generated by generate.py')
      sys.exit(1)

def parseConfig(argv):
      split = argv[1].split(':')
      if len(split) < 2:
            print('Error: unable to parse config')
            usage()

      config_filename = split[0]
      bench = split[1]

      if not os.path.isfile(config_filename):
            print(f'Error: config file `{config_filename}` not found')
            usage()

      with open(config_filename) as configfile:
            lines = configfile.readlines()
            allconfig = eval(''.join(lines))

      if bench not in allconfig:
            print(f'Error: `{bench}` not found in dict generated from `{config_filename}`')
            usage()

      ariel_command = parseAriel(allconfig[bench]['cmd'])
      return ariel_command, allconfig[bench]['directory']

def enableStats():
      # Satatistics
      for i in range(NCORES):
            l1cache[i].enableStatistics(['GetS_recv','CacheHits', 'CacheMisses','TotalEventsReceived','MSHR_occupancy' ])
      core.enableStatistics(['split_read_reqs'])
      l2cache.enableStatistics(['GetS_recv','CacheHits', 'CacheMisses','TotalEventsReceived','MSHR_occupancy' ])

      # Define SST core options
      sst.setProgramOption('timebase', '1ps')
      sst.setStatisticLoadLevel(9)
      #sst.enableAllStatisticsForAllComponents()

      sst.setStatisticOutput('sst.statOutputCSV', {'filepath' : os.path.join(wd,'spectest_stats.csv'), 'separator' : ', ' } )

params = {
      'core' : {
            'verbose'        : 0,
            'corecount'      : NCORES,
            'cachelinesize'  : CACHE_LINE_BYTES,
            'envparamcount'  : 1,
            'envparamname0'  : 'OMP_NUM_THREADS',
            'envparamval0'   : str(NCORES),
            'clock'          : FREQ,
            'arielmode'      : 1,
      },

      'l1cache' : {
            'cache_frequency'       : FREQ,
            'cache_size'            : '4KiB',
            'associativity'         : '4',
            'access_latency_cycles' : '2',
            'L1'                    : '1',
            'cache_line_size'       : CACHE_LINE_BYTES,
            'coherence_protocol'    : COHERENCE,
            'replacement_policy'    : REPLACEMENT,
            'l1prefetcher'            : 'cassini.StridePrefetcher',
            'debug'                 : '0',
      },

      'l2cache' : {
            'access_latency_cycles' : '20',
            'cache_frequency'       : FREQ,
            'replacement_policy'    : REPLACEMENT,
            'coherence_protocol'    : COHERENCE,
            'associativity'         : '4',
            'cache_line_size'       : CACHE_LINE_BYTES,
            'prefetcher'            : 'cassini.StridePrefetcher',
            'debug'                 : '0',
            'L1'                    : '0',
            'cache_size'            : '1MiB',
            'mshr_latency_cycles'   : '5',
      },

      'l1l2bus' : {
            'bus_frequency' : FREQ,
      },

      'memctrl' : {
            'clock'          : FREQ,
            'backing'        : 'none',
            'addr_range_end' : 1024**3-1
      },

      'backend' :  {
            'config_ini'  : f'{os.environ["DRAMSIM3_HOME"]}/configs/HBM2_8Gb_x128.ini',
            'mem_size'    : '8GiB',
      },

}


if __name__ == '__main__':

      if (len(sys.argv) < 2):
            print('Error: Too few args')
            usage()

      if os.getenv('DRAMSIM3_HOME') is None:
            print('Error: DRAMSIM3_HOME not found in environment')
            sys.exit(1)

      ariel_command, directory = parseConfig(sys.argv)
      print(f'Ariel command: {ariel_command}')
      print(f'Ariel directory: {directory}')

      # Save our current directory before chaning to the one that
      # the benchmark needs
      wd = os.getcwd()
      os.chdir(directory)

      # Print run information
      print(f'sdl: {sys.argv}')
      print(f'ariel command: {ariel_command}')

      # Make simulation objects
      core    = sst.Component('Ariel', 'ariel.ariel')
      l1cache = [sst.Component(f'L1Cache_{i}', 'memHierarchy.Cache') for i in range(NCORES)]
      l1l2bus = sst.Component('L1L2Bus', 'memHierarchy.Bus')
      l2cache = sst.Component('L2Cache', 'memHierarchy.Cache')
      memctrl = sst.Component('MemoryController', 'memHierarchy.MemController')
      backend = memctrl.setSubComponent('backend', 'memHierarchy.dramsim3')

      # Set up parameters
      core.addParams(params['core'])
      core.addParams(ariel_command)
      for i in range(NCORES):
            l1cache[i].addParams(params['l1cache'])
      l2cache.addParams(params['l2cache'])
      l1l2bus.addParams(params['l1l2bus'])
      memctrl.addParams(params['memctrl'])
      backend.addParams(params['backend'])

      # Create links
      for i in range(NCORES):
            mklink( (core,       f'cache_link_{i}',   LATENCY),
                    (l1cache[i],  'high_network_0',   LATENCY) )
            mklink( (l1cache[i],  'low_network_0',    LATENCY),
                    (l1l2bus,    f'high_network_{i}', LATENCY))

      mklink( (l1l2bus, 'low_network_0',  LATENCY),
              (l2cache, 'high_network_0', LATENCY) )

      mklink( (l2cache, 'low_network_0', LATENCY),
              (memctrl, 'direct_link',   LATENCY) )

      # Enable statistics
      enableStats()
