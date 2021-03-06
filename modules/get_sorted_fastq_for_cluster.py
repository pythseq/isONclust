from __future__ import print_function
import os,sys
import argparse
import pysam

import operator
import functools

import errno
from time import time

from collections import deque

# def get_kmer_quals(qual, k):
#     return [ qual[i : i + k] for i in range(len(qual) - k +1)]

# def expected_number_of_erroneous_kmers(kmer_quals):
#     sum_of_expectations = 0
#     for kmer in kmer_quals:
#         p_not_error = 1.0 
#         for char_ in set(kmer):
#             p_not_error *= (1 - 10**( - (ord(char_) - 33)/10.0 ))**kmer.count(char_)
#         sum_of_expectations += p_not_error

#     return len(kmer_quals) - sum_of_expectations 

D = {chr(i) : min( 10**( - (ord(chr(i)) - 33)/10.0 ), 0.5)  for i in range(128)}
D_no_min = {chr(i) : 10**( - (ord(chr(i)) - 33)/10.0 )  for i in range(128)}

def expected_number_of_erroneous_kmers_speed(quality_string, k):
    prob_error = [D[char_] for char_ in quality_string]
    window = deque([ (1.0 - p_e) for p_e in prob_error[:k]])
    # print(window)
    qurrent_prob_no_error = functools.reduce(operator.mul, window, 1)
    # print(qurrent_prob_no_error)
    sum_of_expectations = qurrent_prob_no_error # initialization 
    for p_e in prob_error[k:]:
        p_to_leave = window.popleft()
        # print(window)
        # print(p_to_leave, "!" in quality_string)
        qurrent_prob_no_error *= ((1.0 -p_e)/(p_to_leave))
        # print(qurrent_prob_no_error)
        sum_of_expectations += qurrent_prob_no_error
        window.append(1.0 -p_e)
    return len(quality_string) - k + 1 - sum_of_expectations 


# def get_p_no_error_in_kmers_approximate(qual_string, k):
#     poisson_mean = sum([ qual_string.count(char_) * 10**( - (ord(char_) - 33)/10.0 ) for char_ in set(qual_string)])
#     error_rate = poisson_mean/float(len(qual_string))
#     return (1.0 - error_rate)**k #1.0 - min(error_rate * k, 1.0)

# def get_p_error_in_kmer(qual_string, k):
#     poisson_mean = sum([ qual_string.count(char_) * 10**( - (ord(char_) - 33)/10.0 ) for char_ in set(qual_string)])
#     error_rate = poisson_mean/float(len(qual_string))
#     p_error_in_kmer = 1.0 - (1.0 - error_rate)**k
#     return p_error_in_kmer

def readfq(fp): # this is a generator function
    last = None # this is a buffer keeping the last unprocessed line
    while True: # mimic closure; is it a bad idea?
        if not last: # the first record or a record following a fastq
            for l in fp: # search for the start of the next record
                if l[0] in '>@': # fasta/q header line
                    last = l[:-1] # save this line
                    break
        if not last: break
        name, seqs, last = last[1:].replace(" ", "_"), [], None
        for l in fp: # read the sequence
            if l[0] in '@+>':
                last = l[:-1]
                break
            seqs.append(l[:-1])
        if not last or last[0] != '+': # this is a fasta record
            yield name, (''.join(seqs), None) # yield a fasta record
            if not last: break
        else: # this is a fastq record
            seq, leng, seqs = ''.join(seqs), 0, []
            for l in fp: # read the quality
                seqs.append(l[:-1])
                leng += len(l) - 1
                if leng >= len(seq): # have read enough quality
                    last = None
                    yield name, (seq, ''.join(seqs)); # yield a fastq record
                    break
            if last: # reach EOF before reading enough quality
                yield name, (seq, None) # yield a fasta record instead
                break


def reverse_complement(string):
    #rev_nuc = {'A':'T', 'C':'G', 'G':'C', 'T':'A', 'N':'N', 'X':'X'}
    # Modified for Abyss output
    rev_nuc = {'A':'T', 'C':'G', 'G':'C', 'T':'A', 'a':'t', 'c':'g', 'g':'c', 't':'a', 'N':'N', 'X':'X', 'n':'n', 'Y':'R', 'R':'Y', 'K':'M', 'M':'K', 'S':'S', 'W':'W', 'B':'V', 'V':'B', 'H':'D', 'D':'H', 'y':'r', 'r':'y', 'k':'m', 'm':'k', 's':'s', 'w':'w', 'b':'v', 'v':'b', 'h':'d', 'd':'h'}

    rev_comp = ''.join([rev_nuc[nucl] for nucl in reversed(string)])
    return(rev_comp)

def main(args):
    start = time()
    k = args.k
    error_rates = []
    logfile = open(os.path.join(args.outfolder, "logfile.txt"), 'w')
    if os.path.isfile(args.outfile):
        print("Warning, using already existing sorted file in specified directory, in not intended, specify different outfolder or delete the current file.")
        return args.outfile

    elif args.fastq:
        read_array = []
        for i, (acc, (seq, qual)) in enumerate(readfq(open(args.fastq, 'r'))):
            if i % 10000 == 0:
                print(i, "reads processed.")
            
            # kmer_quals = get_kmer_quals(qual, k)
            # exp_errors_in_kmers = expected_number_of_erroneous_kmers(kmer_quals)
            # p_no_error_in_kmers = 1.0 - exp_errors_in_kmers/ float(len(kmer_quals))
            # score =  p_no_error_in_kmers  * (len(seq) - k +1)
            # print("Exact:", p_no_error_in_kmers, score, exp_errors_in_kmers)

            poisson_mean = sum([ qual.count(char_) * D_no_min[char_] for char_ in set(qual)])
            error_rate = poisson_mean/float(len(qual))
            error_rates.append(error_rate)
            exp_errors_in_kmers = expected_number_of_erroneous_kmers_speed(qual, k)
            p_no_error_in_kmers = 1.0 - exp_errors_in_kmers/ float((len(seq) - k +1))
            score =  p_no_error_in_kmers  * (len(seq) - k +1)
            # print("Exact speed:", p_no_error_in_kmers, score, exp_errors_in_kmers)

            # p_no_error_in_kmers_appr =  get_p_no_error_in_kmers_approximate(qual,k)
            # score = p_no_error_in_kmers_appr * (len(seq) - k +1)
            # print("approx:", p_no_error_in_kmers_appr, score)

            # print(sum(p_no_error_in_kmers)/float(len(p_no_error_in_kmers)), p_no_error_in_kmers_appr, qual)
            read_array.append((acc, seq, qual, score) )
        
        read_array.sort(key=lambda x: x[3], reverse=True)
        reads_sorted_outfile = open(args.outfile, "w")
        for i, (acc, seq, qual, score) in enumerate(read_array):
            reads_sorted_outfile.write("@{0}\n{1}\n+\n{2}\n".format(acc + "_{0}".format(score), seq, qual))
        reads_sorted_outfile.close()

        error_rates.sort()
        min_e = error_rates[0]
        max_e = error_rates[-1]
        median_e = error_rates[int(len(error_rates)/2)]
        mean_e = sum(error_rates)/len(error_rates)
        logfile.write("Lowest read error rate:{0}\n".format(min_e))
        logfile.write("Highest read error rate:{0}\n".format(max_e))
        logfile.write("Median read error rate:{0}\n".format(median_e))
        logfile.write("Mean read error rate:{0}\n".format(mean_e))
        logfile.write("\n")
        logfile.close()
        print("Sorted all reads in {0} seconds.".format(time() - start) )
        return reads_sorted_outfile.name

    elif args.flnc and args.ccs:
        flnc_file = pysam.AlignmentFile(args.flnc, "rb", check_sq=False)
        ccs_file = pysam.AlignmentFile(args.ccs, "rb", check_sq=False)
        flnc_dict = {}
        for read in flnc_file.fetch(until_eof=True):
            
            # while quality values are not implemented in unpolished.flnc
            flnc_dict[read.qname] = read.seq
            # If quality values gets implemented, use this one-liner insetead..
            # flnc_dict[read.qname] = (read.seq, read.qual)
        
        read_array = []
        for read in ccs_file.fetch(until_eof=True):
            if read.qname in flnc_dict:
                # while quality values are not implemented in unpolished.flnc
                seq = flnc_dict[read.qname]
                full_seq = read.seq
                full_seq_rc = reverse_complement(full_seq)
                
                if seq in full_seq:
                    start_index = full_seq.index(seq)
                    stop_index = start_index + len(seq)
                    qual = read.qual[start_index: stop_index]

                elif seq in full_seq_rc:
                    qual = read.qual[::-1]
                    start_index = full_seq_rc.index(seq)
                    stop_index = start_index + len(seq)
                    qual = qual[start_index: stop_index]

                else:
                    print("Bug, flnc not in ccs file")
                    sys.exit()

                assert len(qual) == len(seq)

                poisson_mean = sum([ qual.count(char_) * D_no_min[char_] for char_ in set(qual)])
                error_rate = poisson_mean/float(len(qual))
                error_rates.append(error_rate)
                exp_errors_in_kmers = expected_number_of_erroneous_kmers_speed(qual, k)
                p_no_error_in_kmers = 1.0 - exp_errors_in_kmers/ float((len(seq) - k +1))
                score =  p_no_error_in_kmers  * (len(seq) - k +1)

                # p_no_error_in_kmers_appr =  get_p_no_error_in_kmers_approximate(qual,k)
                # score = p_no_error_in_kmers_appr * len(seq)
                read_array.append((read.qname, seq, qual, score) )


                # If quality values gets implemented, simply use the code below and remove everythin above..
                # seq, qual = flnc_dict[read.qname][0], flnc_dict[read.qname][1]
                # p_no_error_in_kmers_appr =  get_p_no_error_in_kmers_approximate(qual,k)
                # score = p_no_error_in_kmers_appr * len(seq)
                # read_array.append((read.qname, seq, qual, score) )

        read_array.sort(key=lambda x: x[3], reverse=True)
        reads_sorted_outfile = open(args.outfile, "w")
        for i, (acc, seq, qual, score) in enumerate(read_array):
            reads_sorted_outfile.write("@{0}\n{1}\n+\n{2}\n".format(acc + "_{0}".format(score), seq, qual))
        reads_sorted_outfile.close()

        error_rates.sort()
        min_e = error_rates[0]
        max_e = error_rates[-1]
        median_e = error_rates[int(len(error_rates)/2)]
        mean_e = sum(error_rates)/len(error_rates)
        logfile.write("Lowest read error rate:{0}\n".format(min_e))
        logfile.write("Highest read error rate:{0}\n".format(max_e))
        logfile.write("Median read error rate:{0}\n".format(median_e))
        logfile.write("Mean read error rate:{0}\n".format(mean_e))
        logfile.write("\n")
        logfile.close()
        print("Sorted all reads in {0} seconds.".format(time() - start) )
        return reads_sorted_outfile.name
    

def mkdir_p(path):
    try:
        os.makedirs(path)
        print("creating", path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Evaluate pacbio IsoSeq transcripts.")
    parser.add_argument('--fastq', type=str,  default=False, help='Path to consensus fastq file(s)')
    parser.add_argument('--flnc', type=str, default=False, help='The flnc reads generated by the isoseq3 algorithm (BAM file)')
    parser.add_argument('--ccs', type=str, default=False, help='Path to lima demultiplexed BAM file')
    parser.add_argument('--outfile', type=str,  default=None, help='A fasta file with transcripts that are shared between samples and have perfect illumina support.')
    parser.add_argument('--k', type=int, default=15, help='kmer size')
    
    args = parser.parse_args()

    if (args.fastq and (args.flnc or args.ccs)):
        print("Either (1) only a fastq file, or (2) a ccs and a flnc file should be specified. ")
        sys.exit()

    if (args.flnc != False and args.ccs == False ) or (args.flnc == False and args.ccs != False ):
        print("qt-clust needs both the ccs.bam file produced by ccs and the flnc file produced by isoseq3 cluster. ")
        sys.exit()


    if len(sys.argv)==1:
        parser.print_help()
        sys.exit()
    path_, file_prefix = os.path.split(args.outfile)
    mkdir_p(path_)

    main(args)