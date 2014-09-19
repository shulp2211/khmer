#! /usr/bin/env python2
#
# This file is part of khmer, http://github.com/ged-lab/khmer/, and is
# Copyright (C) Michigan State University, 2009-2013. It is licensed under
# the three-clause BSD license; see doc/LICENSE.txt.
# Contact: khmer-project@idyll.org
#
"""
Streaming error trimming.

% python sandbox/trim-low-abund.py [ <data1> [ <data2> [ ... ] ] ]

Use -h for parameter help.

TODO: paired support: paired reads should be kept together.
TODO: load/save counting table.
TODO: move output_single elsewhere
"""
import sys
import screed
import os
import khmer
import argparse
import tempfile
import shutil

DEFAULT_NORMALIZE_LIMIT = 20
DEFAULT_CUTOFF = 2

DEFAULT_K = 32
DEFAULT_N_HT = 4
DEFAULT_MIN_HASHSIZE = 1e6


def output_single(read, trim_at=None):
    name = read.name
    sequence = read.sequence

    accuracy = None
    if hasattr(read, 'accuracy'):
        accuracy = read.accuracy

    if trim_at is not None:
        sequence = sequence[:trim_at]
        if accuracy:
            accuracy = accuracy[:trim_at]

    if accuracy:
        return "@%s\n%s\n+\n%s\n" % (name, sequence, accuracy)
    else:
        return ">%s\n%s\n" % (name, sequence)


def main():
    parser = argparse.ArgumentParser(description='XXX')

    env_ksize = os.environ.get('KHMER_KSIZE', DEFAULT_K)
    env_n_hashes = os.environ.get('KHMER_N_HASHES', DEFAULT_N_HT)
    env_hashsize = os.environ.get('KHMER_MIN_HASHSIZE', DEFAULT_MIN_HASHSIZE)

    parser.add_argument('--ksize', '-k', type=int, dest='ksize',
                        default=env_ksize,
                        help='k-mer size to use')
    parser.add_argument('--n_hashes', '-N', type=int, dest='n_hashes',
                        default=env_n_hashes,
                        help='number of hash tables to use')
    parser.add_argument('--hashsize', '-x', type=float, dest='min_hashsize',
                        default=env_hashsize,
                        help='lower bound on hashsize to use')

    parser.add_argument('--cutoff', '-C', type=int, dest='abund_cutoff',
                        help='remove k-mers below this abundance',
                        default=DEFAULT_CUTOFF)

    parser.add_argument('--normalize-to', '-Z', type=int, dest='normalize_to',
                        help='base cutoff on median k-mer abundance of this',
                        default=DEFAULT_NORMALIZE_LIMIT)

    parser.add_argument('--variable-coverage', '-V', action='store_true',
                        dest='variable_coverage', default=False,
                        help='Only trim low-abundance k-mers from sequences '
                        'that have high coverage.')
    parser.add_argument('--tempdir', '-T', type=str, dest='tempdir',
                        default='./')

    parser.add_argument('input_filenames', nargs='+')
    args = parser.parse_args()

    K = args.ksize
    HT_SIZE = args.min_hashsize
    N_HT = args.n_hashes

    CUTOFF = args.abund_cutoff
    NORMALIZE_LIMIT = args.normalize_to

    print 'making hashtable'
    ht = khmer.new_counting_hash(K, HT_SIZE, N_HT)

    tempdir = tempfile.mkdtemp('khmer', 'tmp', args.tempdir)
    print 'created temporary directory %s; use -T to change location' % tempdir

    ###

    save_pass2 = 0

    read_bp = 0
    read_reads = 0
    wrote_bp = 0
    wrote_reads = 0

    pass2list = []
    for filename in args.input_filenames:
        pass2filename = os.path.basename(filename) + '.pass2'
        pass2filename = os.path.join(tempdir, pass2filename)
        trimfilename = os.path.basename(filename) + '.abundtrim'

        pass2list.append((filename, pass2filename, trimfilename))

        pass2fp = open(pass2filename, 'w')
        trimfp = open(trimfilename, 'w')

        for n, read in enumerate(screed.open(filename)):
            if n % 10000 == 0:
                print '...', n, filename, save_pass2, read_reads, read_bp, \
                      wrote_reads, wrote_bp
                
            read_reads += 1
            read_bp += len(read.sequence)
            
            seq = read.sequence.replace('N', 'A')
            med, _, _ = ht.get_median_count(seq)

            # has this portion of the graph saturated? if not,
            # consume & save => pass2.
            if med < NORMALIZE_LIMIT:
                ht.consume(seq)
                pass2fp.write(output_single(read))
                save_pass2 += 1
            else:                       # trim!!
                trim_seq, trim_at = ht.trim_on_abundance(seq, CUTOFF)
                if trim_at >= K:
                    trimfp.write(output_single(read, trim_at))
                    wrote_reads += 1
                    wrote_bp += trim_at

        pass2fp.close()
        trimfp.close()

        print '%s: kept aside %d of %d from first pass, in %s' % \
              (filename, save_pass2, n, filename)

    for orig_filename, pass2filename, trimfilename in pass2list:
        print 'second pass: looking at sequences kept aside in %s' % \
              pass2filename
        for n, read in enumerate(screed.open(pass2filename)):
            if n % 10000 == 0:
                print '... x 2', n, pass2filename, read_reads, read_bp, \
                      wrote_reads, wrote_bp

            trimfp = open(trimfilename, 'a')

            seq = read.sequence.replace('N', 'A')
            med, _, _ = ht.get_median_count(seq)

            if med >= NORMALIZE_LIMIT or not args.variable_coverage:
                trim_seq, trim_at = ht.trim_on_abundance(seq, CUTOFF)
                if trim_at >= K:
                    trimfp.write(output_single(read, trim_at))
                    wrote_reads += 1
                    wrote_bp += trim_at
            else:
                trimfp.write(output_single(read))
                wrote_reads += 1
                wrote_bp += trim_at

        print 'removing %s' % pass2filename
        os.unlink(pass2filename)

    print 'removing temp directory & contents (%s)' % tempdir
    shutil.rmtree(tempdir)

    print 'read %d reads, %d bp' % (read_reads, read_bp,)
    print 'wrote %d reads, %d bp' % (wrote_reads, wrote_bp,)
    print 'trimmed or removed %.2f%% of bases' % ((1 - (wrote_bp / float(read_bp))) * 100.)
    print 'output in *.abundtrim'

if __name__ == '__main__':
    main()
