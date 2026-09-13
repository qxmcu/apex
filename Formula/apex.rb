# typed: false
# frozen_string_literal: true

class Apex < Formula
  desc "Adaptive Tournament Multi-Engine Compression Tool & Next-Gen Container"
  homepage "https://qxmcu.github.io/apex/"
  version "1.1.0"
  license "GPL-3.0-or-later"

  on_macos do
    url "https://github.com/qxmcu/apex/releases/download/v1.1.0/apex-v1.1.0-darwin-x86_64.tar.gz"
    sha256 "0b1b0084b0a84d7369f79b2a0389a54deb9ec1d992ab827ce7ef38dfc1452ba6"
  end

  on_linux do
    if Hardware::CPU.intel?
      url "https://github.com/qxmcu/apex/releases/download/v1.1.0/apex-v1.1.0-linux-x86_64.tar.gz"
      sha256 "4c8d2036c05160893086300a7faae95fa809e530fe71946eb253818e692a8fa2"
    end
  end

  def install
    bin.install "apex"

    # Generate and install shell completions
    generate_completions_from_executable(bin/"apex", "completions")
  end

  test do
    assert_match "apex 1.1.0", shell_output("#{bin}/apex --version")
  end
end
