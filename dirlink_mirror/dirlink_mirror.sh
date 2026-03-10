git# 代码双向同步
brew install opam

opam install unison

nohup unison quick_heketi -repeat 5 -auto -batch > /tmp/unison.log 2>&1 &