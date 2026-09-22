# typed: false
# frozen_string_literal: true

class Apex < Formula
  desc "Adaptive Tournament Multi-Engine Compression Tool & Next-Gen Container"
  homepage "https://qxmcu.github.io/apex/"
  version "1.2.0"
  license "Apache-2.0"

  on_macos do
    url "https://github.com/qxmcu/apex/releases/download/v1.2.0/apex-v1.2.0-darwin-x86_64.tar.gz"
    sha256 "ca1702fbffe565b392b22edced008b372877f7c084a7100e74cec376f534db50"
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/qxmcu/apex/releases/download/v1.2.0/apex-v1.2.0-linux-x86_64.tar.gz"
      sha256 "511b576888a11e4c0aa500d22342543a027b6a7982b1038c463f24a685f47583"
    end
  end

  def install
    bin.install "apex"

    # Generate and install shell completions
    generate_completions_from_executable(bin/"apex", "completions")
  end

  test do
    assert_match "apex 1.2.0", shell_output("#{bin}/apex --version")
  end
end
